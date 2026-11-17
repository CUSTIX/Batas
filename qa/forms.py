from django import forms
from django.conf import settings


class QuestionForm(forms.Form):
    q = forms.CharField(
        label="Your question",
        max_length=settings.QUESTION_MAX_LENGTH,
        min_length=3,
        strip=True,
        widget=forms.TextInput(
            attrs={
                "placeholder": "e.g. Ilang araw ang service incentive leave?",
                "autocomplete": "off",
                "autofocus": True,
            }
        ),
    )
