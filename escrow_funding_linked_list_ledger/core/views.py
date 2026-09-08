import hmac
from decimal import Decimal, ROUND_DOWN

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render

from .forms import (
    ContributionForm,
    ProgressUpdateForm,
    ProgressVoteForm,
    ProjectForm,
    RegistrationForm,
)
from .models import (
    Block,
    FundingStage,
    Profile,
    ProgressUpdate,
    ProgressVote,
    Project,
)


def append_block(
    project,
    sender,
    amount,
    transaction_type,
    stage=None,
    progress_update=None,
):
    last_block = project.blocks.order_by("-block_number").first()

    if last_block is None:
        raise ValueError(
            "A ledger block cannot be created before the Genesis Block."
        )

    return Block.objects.create(
        project=project,
        stage=stage,
        progress_update=progress_update,
        block_number=last_block.block_number + 1,
        sender=sender,
        amount=amount,
        transaction_type=transaction_type,
        previous_hash=last_block.current_hash,
    )


def audit_chain(project):
    expected_previous_hash = "0" * 64
    blocks = list(project.blocks.all())

    if not blocks:
        return {
            "valid": False,
            "block_number": None,
            "reason": "No Genesis Block exists for this campaign.",
        }

    for expected_number, block in enumerate(blocks):
        if block.block_number != expected_number:
            return {
                "valid": False,
                "block_number": block.block_number,
                "reason": (
                    "Block numbering is not sequential. "
                    f"Expected Block #{expected_number}."
                ),
            }

        if not hmac.compare_digest(
            block.previous_hash,
            expected_previous_hash,
        ):
            return {
                "valid": False,
                "block_number": block.block_number,
                "reason": (
                    "The previous hash does not match the "
                    "current hash of the preceding block."
                ),
            }

        calculated_hash = block.compute_hash()

        if not hmac.compare_digest(
            block.current_hash,
            calculated_hash,
        ):
            return {
                "valid": False,
                "block_number": block.block_number,
                "reason": (
                    "The stored hash differs from the calculated hash. "
                    "A protected block value, hash algorithm, or timestamp "
                    "has changed after block creation."
                ),
            }

        expected_previous_hash = block.current_hash

    return {
        "valid": True,
        "block_number": None,
        "reason": "Every block hash and linked-list reference is valid.",
    }


def home(request):
    projects = Project.objects.select_related("creator").all()

    return render(
        request,
        "home.html",
        {
            "projects": projects,
        },
    )


def register(request):
    if request.method == "POST":
        form = RegistrationForm(request.POST)

        if form.is_valid():
            user = form.save()
            login(request, user)

            messages.success(
                request,
                "Your account and $1,000.00 wallet were created.",
            )

            return redirect("home")
    else:
        form = RegistrationForm()

    return render(
        request,
        "registration/register.html",
        {
            "form": form,
        },
    )


@login_required
def create_project(request):
    if request.method == "POST":
        form = ProjectForm(request.POST)

        if form.is_valid():
            with transaction.atomic():
                project = Project.objects.create(
                    creator=request.user,
                    title=form.cleaned_data["title"],
                    description=form.cleaned_data["description"],
                    target_amount=form.cleaned_data["target_amount"],
                )

                for stage_number in range(1, 5):
                    FundingStage.objects.create(
                        project=project,
                        stage_number=stage_number,
                        title=form.cleaned_data[
                            f"stage_{stage_number}_title"
                        ],
                        description=form.cleaned_data[
                            f"stage_{stage_number}_description"
                        ],
                        allocated_amount=form.cleaned_data[
                            f"stage_{stage_number}_amount"
                        ],
                        status=(
                            FundingStage.Status.READY
                            if stage_number == 1
                            else FundingStage.Status.LOCKED
                        ),
                    )

                Block.objects.create(
                    project=project,
                    block_number=0,
                    sender=None,
                    amount=Decimal("0.00"),
                    transaction_type=Block.TransactionType.GENESIS,
                    previous_hash="0" * 64,
                )

            messages.success(
                request,
                "Campaign, Genesis Block, and four funding stages created.",
            )

            return redirect(
                "project_detail",
                project_id=project.id,
            )
    else:
        form = ProjectForm()

    return render(
        request,
        "create_project.html",
        {
            "form": form,
        },
    )


def project_detail(request, project_id):
    project = get_object_or_404(
        Project.objects.select_related("creator"),
        pk=project_id,
    )

    stages = project.stages.all()
    stage_entries = []

    for stage in stages:
        pending_update = stage.progress_updates.filter(
            status=ProgressUpdate.Status.PENDING
        ).first()

        stage_entries.append(
            {
                "stage": stage,
                "pending_update": pending_update,
            }
        )

    current_stage = project.stages.filter(
        status__in=[
            FundingStage.Status.READY,
            FundingStage.Status.VOTING,
        ]
    ).order_by("stage_number").first()

    active_update = None

    if current_stage is not None:
        active_update = current_stage.progress_updates.filter(
            status=ProgressUpdate.Status.PENDING
        ).first()

    is_backer = False
    is_creator = False
    existing_vote = None

    if request.user.is_authenticated:
        is_creator = request.user == project.creator

        is_backer = project.blocks.filter(
            sender=request.user,
            transaction_type=Block.TransactionType.FUND,
        ).exists()

        if active_update is not None:
            existing_vote = active_update.votes.filter(
                voter=request.user
            ).first()

    return render(
        request,
        "project_detail.html",
        {
            "project": project,
            "blocks": project.blocks.select_related(
                "sender",
                "stage",
                "progress_update",
            ).all(),
            "stage_entries": stage_entries,
            "audit": audit_chain(project),
            "contribution_form": ContributionForm(),
            "progress_update_form": ProgressUpdateForm(),
            "progress_vote_form": ProgressVoteForm(
                initial={
                    "choice": existing_vote.choice,
                }
            ) if existing_vote else ProgressVoteForm(),
            "is_backer": is_backer,
            "is_creator": is_creator,
            "current_stage": current_stage,
            "active_update": active_update,
            "has_voted": existing_vote is not None,
        },
    )


@login_required
@transaction.atomic
def contribute(request, project_id):
    project = get_object_or_404(
        Project.objects.select_for_update(),
        pk=project_id,
    )

    if request.method != "POST":
        return redirect(
            "project_detail",
            project_id=project.id,
        )

    form = ContributionForm(request.POST)

    if not form.is_valid():
        messages.error(
            request,
            "Enter a valid contribution amount.",
        )

        return redirect(
            "project_detail",
            project_id=project.id,
        )

    if project.status != Project.Status.ACTIVE:
        messages.error(
            request,
            "This campaign is no longer accepting contributions.",
        )

        return redirect(
            "project_detail",
            project_id=project.id,
        )

    amount = form.cleaned_data["amount"]

    wallet = Profile.objects.select_for_update().get(
        user=request.user
    )

    if wallet.balance < amount:
        messages.error(
            request,
            "Your wallet does not have enough funds.",
        )

        return redirect(
            "project_detail",
            project_id=project.id,
        )

    wallet.balance -= amount
    wallet.save(update_fields=["balance"])

    project.escrow_balance += amount
    project.save(update_fields=["escrow_balance"])

    append_block(
        project=project,
        sender=request.user,
        amount=amount,
        transaction_type=Block.TransactionType.FUND,
    )

    messages.success(
        request,
        "Contribution deposited and recorded in the ledger.",
    )

    return redirect(
        "project_detail",
        project_id=project.id,
    )


@login_required
@transaction.atomic
def submit_progress_update(request, project_id, stage_number):
    project = get_object_or_404(
        Project.objects.select_for_update(),
        pk=project_id,
    )

    stage = get_object_or_404(
        FundingStage.objects.select_for_update(),
        project=project,
        stage_number=stage_number,
    )

    if request.method != "POST":
        return redirect(
            "project_detail",
            project_id=project.id,
        )

    if request.user != project.creator:
        messages.error(
            request,
            "Only the fundraiser can publish a progress update.",
        )

        return redirect(
            "project_detail",
            project_id=project.id,
        )

    if project.status != Project.Status.ACTIVE:
        messages.error(
            request,
            "This campaign has already been resolved.",
        )

        return redirect(
            "project_detail",
            project_id=project.id,
        )

    if stage.status != FundingStage.Status.READY:
        messages.error(
            request,
            "This funding stage is not ready for a progress update.",
        )

        return redirect(
            "project_detail",
            project_id=project.id,
        )

    if stage.rejection_count >= 3:
        messages.error(
            request,
            "This funding stage has reached its maximum rejection limit.",
        )

        return redirect(
            "project_detail",
            project_id=project.id,
        )

    if project.escrow_balance < stage.allocated_amount:
        messages.error(
            request,
            "The escrow balance is not yet sufficient "
            "to fund this stage.",
        )

        return redirect(
            "project_detail",
            project_id=project.id,
        )

    form = ProgressUpdateForm(request.POST)

    if not form.is_valid():
        messages.error(
            request,
            "Enter a valid progress update.",
        )

        return redirect(
            "project_detail",
            project_id=project.id,
        )

    ProgressUpdate.objects.create(
        stage=stage,
        submitted_by=request.user,
        description=form.cleaned_data["description"],
        evidence_url=form.cleaned_data["evidence_url"],
    )

    stage.status = FundingStage.Status.VOTING
    stage.save(update_fields=["status"])

    messages.success(
        request,
        "Progress update published. Backers can now vote.",
    )

    return redirect(
        "project_detail",
        project_id=project.id,
    )


def refund_remaining_escrow(project, stage, progress_update):
    contributions = list(
        project.blocks.filter(
            transaction_type=Block.TransactionType.FUND,
        )
        .values("sender_id")
        .annotate(total_amount=Sum("amount"))
        .order_by("sender_id")
    )

    remaining_escrow = project.escrow_balance

    total_contributed = sum(
        (
            contribution["total_amount"]
            for contribution in contributions
        ),
        Decimal("0.00"),
    )

    if remaining_escrow <= Decimal("0.00"):
        project.status = Project.Status.REFUNDED
        project.save(update_fields=["status"])
        return

    if total_contributed <= Decimal("0.00"):
        raise ValueError(
            "Escrow cannot be refunded because there are no contributions."
        )

    refunded_total = Decimal("0.00")

    for index, contribution in enumerate(contributions):
        is_last_contributor = index == len(contributions) - 1

        if is_last_contributor:
            refund_amount = remaining_escrow - refunded_total
        else:
            refund_amount = (
                remaining_escrow
                * contribution["total_amount"]
                / total_contributed
            ).quantize(
                Decimal("0.01"),
                rounding=ROUND_DOWN,
            )

        contributor_wallet = Profile.objects.select_for_update().get(
            user_id=contribution["sender_id"]
        )

        contributor_wallet.balance += refund_amount
        contributor_wallet.save(update_fields=["balance"])

        append_block(
            project=project,
            sender=contributor_wallet.user,
            amount=refund_amount,
            transaction_type=Block.TransactionType.REFUND,
            stage=stage,
            progress_update=progress_update,
        )

        refunded_total += refund_amount

    project.escrow_balance = Decimal("0.00")
    project.status = Project.Status.REFUNDED
    project.save(
        update_fields=[
            "escrow_balance",
            "status",
        ]
    )


@login_required
@transaction.atomic
def vote_on_progress_update(request, project_id, update_id):
    project = get_object_or_404(
        Project.objects.select_for_update(),
        pk=project_id,
    )

    progress_update = get_object_or_404(
        ProgressUpdate.objects.select_for_update().select_related(
            "stage"
        ),
        pk=update_id,
        stage__project=project,
    )

    stage = progress_update.stage

    if request.method != "POST":
        return redirect(
            "project_detail",
            project_id=project.id,
        )

    if project.status != Project.Status.ACTIVE:
        messages.error(
            request,
            "This campaign has already been resolved.",
        )

        return redirect(
            "project_detail",
            project_id=project.id,
        )

    if stage.status != FundingStage.Status.VOTING:
        messages.error(
            request,
            "This funding stage is not currently open for voting.",
        )

        return redirect(
            "project_detail",
            project_id=project.id,
        )

    if progress_update.status != ProgressUpdate.Status.PENDING:
        messages.error(
            request,
            "This progress update has already been resolved.",
        )

        return redirect(
            "project_detail",
            project_id=project.id,
        )

    is_backer = project.blocks.filter(
        sender=request.user,
        transaction_type=Block.TransactionType.FUND,
    ).exists()

    if not is_backer:
        messages.error(
            request,
            "Only contributors to this campaign can vote.",
        )

        return redirect(
            "project_detail",
            project_id=project.id,
        )

    form = ProgressVoteForm(request.POST)

    if not form.is_valid():
        messages.error(
            request,
            "Choose Approve or Reject before submitting your vote.",
        )

        return redirect(
            "project_detail",
            project_id=project.id,
        )

    ProgressVote.objects.update_or_create(
        progress_update=progress_update,
        voter=request.user,
        defaults={
            "choice": form.cleaned_data["choice"],
        },
    )

    backer_count = project.blocks.filter(
        transaction_type=Block.TransactionType.FUND,
    ).values("sender_id").distinct().count()

    green_votes = progress_update.votes.filter(
        choice=ProgressVote.Choice.GREEN,
    ).count()

    red_votes = progress_update.votes.filter(
        choice=ProgressVote.Choice.RED,
    ).count()

    if green_votes > backer_count / 2:
        release_amount = (
            stage.allocated_amount - stage.released_amount
        )

        if project.escrow_balance < release_amount:
            messages.error(
                request,
                "Escrow funds are insufficient for this stage release.",
            )

            return redirect(
                "project_detail",
                project_id=project.id,
            )

        fundraiser_wallet = Profile.objects.select_for_update().get(
            user=project.creator
        )

        fundraiser_wallet.balance += release_amount
        fundraiser_wallet.save(update_fields=["balance"])

        project.escrow_balance -= release_amount
        project.total_released_amount += release_amount
        project.save(
            update_fields=[
                "escrow_balance",
                "total_released_amount",
            ]
        )

        stage.released_amount += release_amount
        stage.status = FundingStage.Status.RELEASED
        stage.save(
            update_fields=[
                "released_amount",
                "status",
            ]
        )

        progress_update.status = ProgressUpdate.Status.APPROVED
        progress_update.save(update_fields=["status"])

        append_block(
            project=project,
            sender=project.creator,
            amount=release_amount,
            transaction_type=Block.TransactionType.RELEASE,
            stage=stage,
            progress_update=progress_update,
        )

        next_stage = project.stages.filter(
            stage_number=stage.stage_number + 1,
            status=FundingStage.Status.LOCKED,
        ).first()

        if next_stage is not None:
            next_stage.status = FundingStage.Status.READY
            next_stage.save(update_fields=["status"])
        else:
            project.status = Project.Status.COMPLETED
            project.save(update_fields=["status"])

        messages.success(
            request,
            f"Stage {stage.stage_number} was approved and "
            f"${release_amount} was released to the fundraiser.",
        )

    elif red_votes > backer_count / 2:
        progress_update.status = ProgressUpdate.Status.REJECTED
        progress_update.save(update_fields=["status"])

        stage.rejection_count += 1

        if stage.rejection_count >= 3:
            stage.status = FundingStage.Status.FAILED
            stage.save(
                update_fields=[
                    "rejection_count",
                    "status",
                ]
            )

            refund_remaining_escrow(
                project=project,
                stage=stage,
                progress_update=progress_update,
            )

            messages.success(
                request,
                "This progress stage was rejected three times. "
                "All remaining escrow funds were refunded "
                "proportionally to fund providers.",
            )
        else:
            stage.status = FundingStage.Status.READY
            stage.save(
                update_fields=[
                    "rejection_count",
                    "status",
                ]
            )

            remaining_retries = 3 - stage.rejection_count

            messages.success(
                request,
                "The progress update was rejected. "
                f"The fundraiser has {remaining_retries} "
                "progress-update attempt(s) remaining.",
            )

    else:
        messages.success(
            request,
            "Vote recorded. The progress update is awaiting a majority.",
        )

    return redirect(
        "project_detail",
        project_id=project.id,
    )