from django import forms

from .models import Note, Position


class NoteForm(forms.ModelForm):
    class Meta:
        model = Note
        fields = ['text']


class PositionsForm(forms.ModelForm):
    class Meta:
        model = Position
        fields = ['data']
