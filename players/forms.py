from django import forms

from .models import Note, Position
from .utils import POSITIONS


class NoteForm(forms.ModelForm):
    class Meta:
        model = Note
        fields = ["text"]


class PositionsForm(forms.ModelForm):
    check = forms.MultipleChoiceField(
        choices=[(code, code) for code in POSITIONS[1:5]], required=False
    )

    class Meta:
        model = Position
        fields = []
