from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm, UsernameField
from .models import Profile
from users.choices import *


class UserRegisterForm(UserCreationForm):
    email = forms.EmailField()

    class Meta:
        model = User
        fields = ["username", "email", "password1", "password2"]


class UserUpdateForm(forms.ModelForm):
    email = forms.EmailField()

    class Meta:
        model = User
        fields = ["username", "email"]
        field_classes = {"username": UsernameField}

    def clean_username(self):
        username = self.cleaned_data["username"]
        if User.objects.filter(username__iexact=username).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError(self.instance.unique_error_message(User, ["username"]))
        return username

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            # Profile edits must not restore an old password/last-login snapshot.
            user.save(
                update_fields=[field for field in self.Meta.fields if field in self.cleaned_data]
            )
            self.save_m2m()
        return user


class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ["image"]


class MeasurementsFormatEdit(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ["measurements_format"]
