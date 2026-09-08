from decimal import Decimal

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import ProgressVote, Vote


class RegistrationForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
            }
        ),
    )

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")


class ProjectForm(forms.Form):
    title = forms.CharField(
        max_length=160,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
            }
        ),
    )
    description = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 5,
            }
        ),
    )
    target_amount = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "min": "0.01",
                "step": "0.01",
            }
        ),
    )

    stage_1_title = forms.CharField(
        max_length=160,
        label="Stage 1 Title",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
            }
        ),
    )
    stage_1_description = forms.CharField(
        label="Stage 1 Description",
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
            }
        ),
    )
    stage_1_amount = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
        label="Stage 1 Funding Amount",
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "min": "0.01",
                "step": "0.01",
            }
        ),
    )

    stage_2_title = forms.CharField(
        max_length=160,
        label="Stage 2 Title",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
            }
        ),
    )
    stage_2_description = forms.CharField(
        label="Stage 2 Description",
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
            }
        ),
    )
    stage_2_amount = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
        label="Stage 2 Funding Amount",
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "min": "0.01",
                "step": "0.01",
            }
        ),
    )

    stage_3_title = forms.CharField(
        max_length=160,
        label="Stage 3 Title",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
            }
        ),
    )
    stage_3_description = forms.CharField(
        label="Stage 3 Description",
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
            }
        ),
    )
    stage_3_amount = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
        label="Stage 3 Funding Amount",
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "min": "0.01",
                "step": "0.01",
            }
        ),
    )

    stage_4_title = forms.CharField(
        max_length=160,
        label="Stage 4 Title",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
            }
        ),
    )
    stage_4_description = forms.CharField(
        label="Stage 4 Description",
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
            }
        ),
    )
    stage_4_amount = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
        label="Stage 4 Funding Amount",
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "min": "0.01",
                "step": "0.01",
            }
        ),
    )

    def clean(self):
        cleaned_data = super().clean()

        target_amount = cleaned_data.get("target_amount")

        stage_amounts = [
            cleaned_data.get("stage_1_amount"),
            cleaned_data.get("stage_2_amount"),
            cleaned_data.get("stage_3_amount"),
            cleaned_data.get("stage_4_amount"),
        ]

        if target_amount is None or any(
            amount is None for amount in stage_amounts
        ):
            return cleaned_data

        total_stage_amount = sum(stage_amounts, Decimal("0.00"))

        if total_stage_amount != target_amount:
            raise forms.ValidationError(
                "The four stage amounts must total exactly "
                "the project target amount."
            )

        return cleaned_data


class ContributionForm(forms.Form):
    amount = forms.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "min": "0.01",
                "step": "0.01",
            }
        ),
    )


class VoteForm(forms.Form):
    choice = forms.ChoiceField(
        choices=Vote.Choice.choices,
        widget=forms.RadioSelect,
    )


class ProgressUpdateForm(forms.Form):
    description = forms.CharField(
        label="Progress Update",
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 5,
            }
        ),
    )
    evidence_url = forms.URLField(
        required=False,
        label="Evidence Link",
        widget=forms.URLInput(
            attrs={
                "class": "form-control",
                "placeholder": "https://example.com/proof",
            }
        ),
    )


class ProgressVoteForm(forms.Form):
    choice = forms.ChoiceField(
        choices=ProgressVote.Choice.choices,
        widget=forms.RadioSelect,
    )