import hmac
from django.core.exceptions import ValidationError

import hashlib
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone


class Profile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    balance = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("1000.00"),
    )

    def __str__(self):
        return f"{self.user.username} wallet"


class Project(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        COMPLETED = "COMPLETED", "Completed"
        REFUNDED = "REFUNDED", "Refunded"

    creator = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="projects",
    )
    title = models.CharField(max_length=160)
    description = models.TextField()
    target_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
    )
    escrow_balance = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    total_released_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class FundingStage(models.Model):
    class Status(models.TextChoices):
        AWAITING_FUNDING = "AWAITING", "Awaiting Stage 1 Funding"
        LOCKED = "LOCKED", "Locked"
        READY = "READY", "Ready for Progress Update"
        VOTING = "VOTING", "Voting in Progress"
        RELEASED = "RELEASED", "Released"
        FAILED = "FAILED", "Failed and Refunded"

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="stages",
    )
    stage_number = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=160)
    description = models.TextField()
    allocated_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
    )
    released_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    rejection_count = models.PositiveSmallIntegerField(
    default=0,
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.LOCKED,
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["stage_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "stage_number"],
                name="unique_project_stage_number",
            ),
            models.CheckConstraint(
                condition=models.Q(stage_number__gte=1)
                & models.Q(stage_number__lte=4),
                name="stage_number_between_one_and_four",
            ),
        ]

    def __str__(self):
        return f"{self.project.title} — Stage {self.stage_number}"


class ProgressUpdate(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending Vote"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    stage = models.ForeignKey(
        FundingStage,
        on_delete=models.CASCADE,
        related_name="progress_updates",
    )
    submitted_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="progress_updates",
    )
    description = models.TextField()
    evidence_url = models.URLField(blank=True)
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"{self.stage.project.title} — "
            f"Stage {self.stage.stage_number} update"
        )


class Block(models.Model):
    class TransactionType(models.TextChoices):
        GENESIS = "GENESIS", "Genesis"
        FUND = "FUND", "Funding Deposit"
        RELEASE = "RELEASE", "Stage Release"
        REFUND = "REFUND", "Backer Refund"

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="blocks",
    )
    stage = models.ForeignKey(
        FundingStage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="release_blocks",
    )
    progress_update = models.ForeignKey(
        ProgressUpdate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="release_blocks",
    )
    block_number = models.PositiveIntegerField()
    sender = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ledger_blocks",
    )
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    transaction_type = models.CharField(
        max_length=10,
        choices=TransactionType.choices,
    )
    previous_hash = models.CharField(max_length=64)
    current_hash = models.CharField(max_length=64, editable=False)
    created_at = models.DateTimeField(
    default=timezone.now,
    editable=False,
    )

    class Meta:
        ordering = ["block_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "block_number"],
                name="unique_project_block_number",
            )
        ]

    def compute_hash(self):
        sender_id = self.sender_id if self.sender_id is not None else "None"

        value = (
            f"{self.previous_hash}"
            f"{sender_id}"
            f"{self.amount}"
            f"{self.transaction_type}"
            f"{self.created_at.isoformat()}"
        )

        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def save(self, *args, **kwargs):
        if self._state.adding:
            if self.created_at is None:
                self.created_at = timezone.now()

            self.current_hash = self.compute_hash()

        else:
            original = Block.objects.get(pk=self.pk)

            protected_fields = [
                "project_id",
                "stage_id",
                "progress_update_id",
                "block_number",
                "sender_id",
                "amount",
                "transaction_type",
                "previous_hash",
                "current_hash",
                "created_at",
            ]

            for field_name in protected_fields:
                if getattr(self, field_name) != getattr(
                    original,
                    field_name,
                ):
                    raise ValidationError(
                        "Ledger blocks are immutable and cannot be edited."
                    )

        super().save(*args, **kwargs)
        
    def __str__(self):
        return f"{self.project.title} — Block #{self.block_number}"


class Vote(models.Model):
    class Choice(models.TextChoices):
        GREEN = "GREEN", "Approve"
        RED = "RED", "Reject"

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="votes",
    )
    voter = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="escrow_votes",
    )
    choice = models.CharField(
        max_length=5,
        choices=Choice.choices,
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["project", "voter"],
                name="one_vote_per_project_user",
            )
        ]

    def __str__(self):
        return f"{self.voter.username}: {self.choice}"


class ProgressVote(models.Model):
    class Choice(models.TextChoices):
        GREEN = "GREEN", "Approve"
        RED = "RED", "Reject"

    progress_update = models.ForeignKey(
        ProgressUpdate,
        on_delete=models.CASCADE,
        related_name="votes",
    )
    voter = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="progress_votes",
    )
    choice = models.CharField(
        max_length=5,
        choices=Choice.choices,
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["progress_update", "voter"],
                name="one_vote_per_progress_update_user",
            )
        ]

    def __str__(self):
        return f"{self.voter.username}: {self.choice}"


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(
            user=instance,
            balance=Decimal("1000.00"),
        )