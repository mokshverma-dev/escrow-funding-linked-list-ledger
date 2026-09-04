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
        RELEASED = "RELEASED", "Released"
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


class Block(models.Model):
    class TransactionType(models.TextChoices):
        GENESIS = "GENESIS", "Genesis"
        FUND = "FUND", "Funding Deposit"
        RELEASE = "RELEASE", "Escrow Release"
        REFUND = "REFUND", "Backer Refund"

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="blocks",
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
    created_at = models.DateTimeField(default=timezone.now)

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
        self.current_hash = self.compute_hash()
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
    

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(
            user=instance,
            balance=Decimal("1000.00"),
        )