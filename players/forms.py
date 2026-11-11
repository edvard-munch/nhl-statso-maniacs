from django import forms

from .models import Note, Position
from .utils import POSITIONS


PRIVATE_POSITION_CHOICES = tuple((code, code) for code in POSITIONS[1:5])


class NoteForm(forms.ModelForm):
    class Meta:
        model = Note
        fields = ["text"]


class PositionsForm(forms.ModelForm):
    check = forms.MultipleChoiceField(choices=PRIVATE_POSITION_CHOICES, required=False)

    class Meta:
        model = Position
        fields = []
