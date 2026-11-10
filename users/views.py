from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .forms import UserRegisterForm, UserUpdateForm, ProfileUpdateForm, MeasurementsFormatEdit
from .registration import create_registered_user
from django.contrib.auth.views import PasswordResetConfirmView


def register(request):
    if request.method == "POST":
        form = UserRegisterForm(request.POST)
        if create_registered_user(form) is not None:
            username = form.cleaned_data.get("username")
            messages.success(
                request, f"{username}, your account is created! You are now able to log in"
            )
            return redirect("login")
    else:
        form = UserRegisterForm()
    return render(request, "users/register.html", {"form": form})


def bookmark_message(request):
    return render(request, "users/bookmark_message.html", {"title": "Message"})


@login_required
def profile(request):
    if request.method == "POST":
        u_form = UserUpdateForm(request.POST, instance=request.user)
        p_form = ProfileUpdateForm(request.POST, request.FILES, instance=request.user.profile)
        ms_form = MeasurementsFormatEdit(request.POST, instance=request.user.profile)

        if u_form.is_valid() and p_form.is_valid() and ms_form.is_valid():
            u_form.save()
            p_form.save()
            ms_form.save()
            username = u_form.cleaned_data.get("username")
            messages.success(request, f"{username}, your account has been updated!")
            return redirect("profile")

    else:
        u_form = UserUpdateForm(instance=request.user)
        p_form = ProfileUpdateForm(instance=request.user.profile)
        ms_form = MeasurementsFormatEdit(instance=request.user.profile)

    context = {
        "u_form": u_form,
        "p_form": p_form,
        "ms_form": ms_form,
    }

    return render(request, "users/profile.html", context)


class AtomicPasswordResetConfirmView(PasswordResetConfirmView):
    """Keep HTML token exchange/rendering, but consume tokens with the API lock."""

    def get_user(self, uidb64):
        from .password_recovery import InvalidResetLink, user_from_uid

        try:
            user = user_from_uid(uidb64)
        except InvalidResetLink:
            return None
        return user if user.is_active and user.has_usable_password() else None

    def form_valid(self, form):
        from django.contrib.auth import login as auth_login
        from django.contrib.auth.views import INTERNAL_RESET_SESSION_TOKEN
        from django.http import HttpResponseRedirect
        from .password_recovery import InvalidResetLink, consume_reset_link

        try:
            current_form, user = consume_reset_link(
                self.kwargs["uidb64"],
                self.request.session.get(INTERNAL_RESET_SESSION_TOKEN),
                self.request.POST,
                form_class=self.get_form_class(),
                token_generator=self.token_generator,
            )
        except InvalidResetLink:
            self.validlink = False
            return self.render_to_response(self.get_context_data())
        if user is None:
            return self.form_invalid(current_form)
        self.request.session.pop(INTERNAL_RESET_SESSION_TOKEN, None)
        if self.post_reset_login:
            auth_login(self.request, user, self.post_reset_login_backend)
        return HttpResponseRedirect(self.get_success_url())
