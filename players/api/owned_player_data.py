"""Session-private typed note and position resources, sharing legacy validation/writers."""

from collections.abc import Mapping

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from nhl_web_app.api.auth_views import CSRF_HEADER, json_body
from nhl_web_app.api.auth_serializers import LoginTextField
from nhl_web_app.api.errors import PrivatePlayerDataConflict
from players import owned_data
from players.forms import NoteForm, PositionsForm, PRIVATE_POSITION_CHOICES
from players.models import Note, Position
from players.saved_actions import locked_user
from .saved_lists import membership_target
from .saved_views import (
    PrivateSavedListView,
    SAVED_LIST_ERRORS,
    TYPED_PATH,
    validate_empty_mutation,
)
from .serializers import StrictQuerySerializer

NOTE_MAX_LENGTH = Note._meta.get_field("text").max_length


class PrivateInputSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            unknown = {key: ["Unsupported field."] for key in data if key not in self.fields}
            if unknown:
                raise ValidationError(unknown)
        return super().to_internal_value(data)


class NoteInputSerializer(PrivateInputSerializer):
    text = LoginTextField(max_length=NOTE_MAX_LENGTH, allow_blank=True)

    def validate_text(self, value):
        form = NoteForm({"text": value})
        if not form.is_valid():
            raise ValidationError(list(form.errors["text"]))
        return form.cleaned_data["text"]


class PositionsInputSerializer(PrivateInputSerializer):
    positions = serializers.ListField(
        child=serializers.ChoiceField(choices=PRIVATE_POSITION_CHOICES), allow_empty=True
    )

    def validate_positions(self, value):
        form = PositionsForm({"check": value})
        if not form.is_valid():
            raise ValidationError(list(form.errors["check"]))
        return list(dict.fromkeys(form.cleaned_data["check"]))


class OwnedPlayerIdentitySerializer(serializers.Serializer):
    player_type = serializers.ChoiceField(choices=["skater", "goalie"])
    nhl_id = serializers.IntegerField()
    source = serializers.ChoiceField(choices=owned_data.SOURCES)


class PrivateNoteSerializer(OwnedPlayerIdentitySerializer):
    text = serializers.CharField(allow_blank=True, allow_null=True, max_length=NOTE_MAX_LENGTH)


class PrivatePositionsSerializer(OwnedPlayerIdentitySerializer):
    positions = serializers.ListField(
        child=serializers.ChoiceField(choices=PRIVATE_POSITION_CHOICES), allow_null=True
    )
    official_position = serializers.CharField(allow_blank=True)
    effective_positions = serializers.ListField(child=serializers.CharField())


def player_target(player_type, nhl_id):
    model = membership_target(player_type, nhl_id)
    return get_object_or_404(model.objects.only("nhl_id", "name", "position_abbr"), nhl_id=nhl_id)


def private_data(owner, player, player_type, model):
    selected = owned_data.lookup(owner, player, model)
    data = {"player_type": player_type, "nhl_id": player.nhl_id, "source": selected.source}
    if model is Note:
        return {**data, "text": selected.record.text if selected.record is not None else None}
    positions = None
    if selected.record is not None:
        raw = selected.record.data
        form = PositionsForm({"check": raw})
        if isinstance(raw, list) and form.is_valid() and raw:
            positions = list(dict.fromkeys(form.cleaned_data["check"]))
        else:
            data["source"] = owned_data.INVALID
    return {
        **data,
        "positions": positions,
        "official_position": player.position_abbr,
        "effective_positions": positions
        if positions is not None
        else [player.position_abbr]
        if player.position_abbr
        else [],
    }


class PrivatePlayerResource(PrivateSavedListView):
    def read(self, request, player_type, nhl_id):
        query = StrictQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        with locked_user(request.user) as owner:
            player = player_target(player_type, nhl_id)
            return Response(
                self.response_serializer(private_data(owner, player, player_type, self.model)).data
            )

    def replace(self, request, player_type, nhl_id):
        query = StrictQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        payload = self.input_serializer(data=json_body(request))
        payload.is_valid(raise_exception=True)
        with locked_user(request.user) as owner:
            player = player_target(player_type, nhl_id)
            try:
                owned_data.replace(
                    owner, player, self.model, payload.validated_data[self.value_field]
                )
            except owned_data.OwnedDataConflict:
                raise PrivatePlayerDataConflict() from None
            return Response(
                self.response_serializer(private_data(owner, player, player_type, self.model)).data
            )

    def clear(self, request, player_type, nhl_id):
        validate_empty_mutation(request)
        with locked_user(request.user) as owner:
            player = player_target(player_type, nhl_id)
            try:
                owned_data.replace(owner, player, self.model, "" if self.model is Note else [])
            except owned_data.OwnedDataConflict:
                raise PrivatePlayerDataConflict() from None
            return Response(status=status.HTTP_204_NO_CONTENT)


class PrivateNoteView(PrivatePlayerResource):
    model = Note
    input_serializer = NoteInputSerializer
    response_serializer = PrivateNoteSerializer
    value_field = "text"

    @extend_schema(
        operation_id="me_player_note_retrieve",
        tags=["private-players"],
        parameters=[TYPED_PATH],
        responses={status.HTTP_200_OK: PrivateNoteSerializer, **SAVED_LIST_ERRORS},
        description="Current account's typed player note. No queries. Null text for absent/ambiguous records; safe untyped legacy lookup only when uniquely attributable. No domain writes on reads, no public statistics fallback.",
    )
    def get(self, request, player_type, nhl_id):
        return self.read(request, player_type, nhl_id)

    @extend_schema(
        operation_id="me_player_note_put",
        tags=["private-players"],
        parameters=[TYPED_PATH, CSRF_HEADER],
        request=NoteInputSerializer,
        responses={status.HTTP_200_OK: PrivateNoteSerializer, **SAVED_LIST_ERRORS},
        description="Explicit full note replacement, trimmed maximum 400 characters using legacy form policy. Empty text clears. Current account and typed player only; requires session/CSRF, rejects unknown fields/queries. Shares owner lock with legacy editor; typed duplicates return 409 private_player_data_conflict. Serializes within the transaction.",
    )
    def put(self, request, player_type, nhl_id):
        return self.replace(request, player_type, nhl_id)

    @extend_schema(
        operation_id="me_player_note_delete",
        tags=["private-players"],
        parameters=[TYPED_PATH, CSRF_HEADER],
        request=None,
        responses={status.HTTP_204_NO_CONTENT: None, **SAVED_LIST_ERRORS},
        description="Clear the current account's safely attributable note records, 204 including already absent. Existing player required; unknown typed player is 404. Ambiguous untyped rows are preserved; typed duplicates conflict with 409. Requires session/CSRF, empty body/JSON object only and no queries.",
    )
    def delete(self, request, player_type, nhl_id):
        return self.clear(request, player_type, nhl_id)


class PrivatePositionsView(PrivatePlayerResource):
    model = Position
    input_serializer = PositionsInputSerializer
    response_serializer = PrivatePositionsSerializer
    value_field = "positions"

    @extend_schema(
        operation_id="me_player_positions_retrieve",
        tags=["private-players"],
        parameters=[TYPED_PATH],
        responses={status.HTTP_200_OK: PrivatePositionsSerializer, **SAVED_LIST_ERRORS},
        description="Current account's private position override, official saved position and effective values. Null override for absent/ambiguous/invalid records; official metadata supplies the fallback. No queries, NHL calls or domain writes.",
    )
    def get(self, request, player_type, nhl_id):
        return self.read(request, player_type, nhl_id)

    @extend_schema(
        operation_id="me_player_positions_put",
        tags=["private-players"],
        parameters=[TYPED_PATH, CSRF_HEADER],
        request=PositionsInputSerializer,
        responses={status.HTTP_200_OK: PrivatePositionsSerializer, **SAVED_LIST_ERRORS},
        description="Full position override replacement using existing D/C/LW/RW choices for both typed models; duplicates removed preserving input order. Empty array clears. No official position or public statistics changes. Session/CSRF, strict JSON fields, no queries; shares owner lock with legacy writer, typed duplicates return 409 private_player_data_conflict.",
    )
    def put(self, request, player_type, nhl_id):
        return self.replace(request, player_type, nhl_id)

    @extend_schema(
        operation_id="me_player_positions_delete",
        tags=["private-players"],
        parameters=[TYPED_PATH, CSRF_HEADER],
        request=None,
        responses={status.HTTP_204_NO_CONTENT: None, **SAVED_LIST_ERRORS},
        description="Clear safely attributable private positions, 204 including already absent; official metadata remains unchanged. Existing typed player required (404 otherwise). Ambiguous untyped rows are preserved; typed duplicates return 409. Session/CSRF, empty body/JSON object only, no queries.",
    )
    def delete(self, request, player_type, nhl_id):
        return self.clear(request, player_type, nhl_id)
