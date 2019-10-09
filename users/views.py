from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .forms import UserRegisterForm, UserUpdateForm, ProfileUpdateForm, MeasurementsFormatEdit


def register(request):
    if request.method == 'POST':
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            form.save()
            username = form.cleaned_data.get('username')
            messages.success(request, f'{username}, your account is created! You are now able to log in')
            return redirect('login')
    else:
        form = UserRegisterForm()
    return render(request, 'users/register.html', {'form': form})


def bookmark_message(request):
    return render(request, 'users/bookmark_message.html', {'title': 'Message'})


@login_required
def profile(request):
    if request.method == 'POST':
        u_form = UserUpdateForm(request.POST, instance=request.user)
        p_form = ProfileUpdateForm(request.POST,
                                   request.FILES,
                                   instance=request.user.profile)
        ms_form = MeasurementsFormatEdit(request.POST, instance=request.user.profile)
        print(u_form)
        print(p_form)
        print(ms_form)

        if u_form.is_valid() and p_form.is_valid() and ms_form.is_valid():
            u_form.save()
            p_form.save()
            ms_form.save()
            username = u_form.cleaned_data.get('username')
            messages.success(request, f'{username}, your account has been updated!')
            return redirect('profile')

    else:
        u_form = UserUpdateForm(instance=request.user)
        p_form = ProfileUpdateForm(instance=request.user.profile)
        ms_form = MeasurementsFormatEdit(instance=request.user.profile)

    context = {
        'u_form': u_form,
        'p_form': p_form,
        'ms_form': ms_form,
    }

    return render(request, 'users/profile.html', context)
