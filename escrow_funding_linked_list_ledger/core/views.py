from decimal import Decimal, ROUND_DOWN

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ContributionForm, ProjectForm, RegistrationForm, VoteForm
from .models import Block, FundingStage, Profile, Project, Vote


def append_block(project, sender, amount, transaction_type):
    last_block = project.blocks.order_by("-block_number").first()

    return Block.objects.create(
        project=project,
        block_number=last_block.block_number + 1,
        sender=sender,
        amount=amount,
        transaction_type=transaction_type,
        previous_hash=last_block.current_hash,
    )


def is_chain_valid(project):
    expected_previous_hash = "0" * 64
    blocks = list(project.blocks.all())

    if not blocks:
        return False

    for expected_number, block in enumerate(blocks):
        if block.block_number != expected_number:
            return False

        if block.previous_hash != expected_previous_hash:
            return False

        if block.current_hash != block.compute_hash():
            return False

        expected_previous_hash = block.current_hash

    return True


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

    is_backer = False
    current_vote = None

    if request.user.is_authenticated:
        is_backer = project.blocks.filter(
            sender=request.user,
            transaction_type=Block.TransactionType.FUND,
        ).exists()

        current_vote = project.votes.filter(
            voter=request.user
        ).first()

    return render(
        request,
        "project_detail.html",
        {
            "project": project,
            "blocks": project.blocks.select_related("sender").all(),
            "verified": is_chain_valid(project),
            "contribution_form": ContributionForm(),
            "vote_form": VoteForm(
                initial={
                    "choice": current_vote.choice
                }
            ) if current_vote else VoteForm(),
            "is_backer": is_backer,
            "has_voted": current_vote is not None,
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
def cast_vote(request, project_id):
    project = get_object_or_404(
        Project.objects.select_for_update(),
        pk=project_id,
    )

    if request.method != "POST":
        return redirect(
            "project_detail",
            project_id=project.id,
        )

    form = VoteForm(request.POST)

    if not form.is_valid():
        messages.error(request, "Select an approval or rejection vote.")

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

    is_backer = project.blocks.filter(
        sender=request.user,
        transaction_type=Block.TransactionType.FUND,
    ).exists()

    if not is_backer:
        messages.error(
            request,
            "Only campaign backers can vote.",
        )

        return redirect(
            "project_detail",
            project_id=project.id,
        )

    Vote.objects.update_or_create(
        project=project,
        voter=request.user,
        defaults={
            "choice": form.cleaned_data["choice"],
        },
    )

    backer_count = project.blocks.filter(
        transaction_type=Block.TransactionType.FUND,
    ).values("sender_id").distinct().count()

    green_votes = project.votes.filter(
        choice=Vote.Choice.GREEN
    ).count()

    red_votes = project.votes.filter(
        choice=Vote.Choice.RED
    ).count()

    if green_votes > backer_count / 2:
        creator_wallet = Profile.objects.select_for_update().get(
            user=project.creator
        )

        released_amount = project.escrow_balance

        creator_wallet.balance += released_amount
        creator_wallet.save(update_fields=["balance"])

        append_block(
            project=project,
            sender=project.creator,
            amount=released_amount,
            transaction_type=Block.TransactionType.RELEASE,
        )

        project.escrow_balance = Decimal("0.00")
        project.status = Project.Status.RELEASED
        project.save(
            update_fields=[
                "escrow_balance",
                "status",
            ]
        )

        messages.success(
            request,
            "Majority approval released escrow to the creator.",
        )

    elif red_votes > backer_count / 2:
        deposits = list(
            project.blocks.filter(
                transaction_type=Block.TransactionType.FUND
            )
            .values("sender_id")
            .annotate(total_amount=Sum("amount"))
        )

        escrow_amount = project.escrow_balance
        total_contributed = sum(
            (
                deposit["total_amount"]
                for deposit in deposits
            ),
            Decimal("0.00"),
        )

        total_refunded = Decimal("0.00")

        for index, deposit in enumerate(deposits):
            is_final_backer = index == len(deposits) - 1

            if is_final_backer:
                refund_amount = escrow_amount - total_refunded
            else:
                refund_amount = (
                    escrow_amount
                    * deposit["total_amount"]
                    / total_contributed
                ).quantize(
                    Decimal("0.01"),
                    rounding=ROUND_DOWN,
                )

            backer_wallet = Profile.objects.select_for_update().get(
                user_id=deposit["sender_id"]
            )

            backer_wallet.balance += refund_amount
            backer_wallet.save(update_fields=["balance"])

            total_refunded += refund_amount

        append_block(
            project=project,
            sender=None,
            amount=escrow_amount,
            transaction_type=Block.TransactionType.REFUND,
        )

        project.escrow_balance = Decimal("0.00")
        project.status = Project.Status.REFUNDED
        project.save(
            update_fields=[
                "escrow_balance",
                "status",
            ]
        )

        messages.success(
            request,
            "Majority rejection refunded backers proportionally.",
        )

    else:
        messages.success(
            request,
            "Vote recorded. The campaign is awaiting a majority.",
        )

    return redirect(
        "project_detail",
        project_id=project.id,
    )