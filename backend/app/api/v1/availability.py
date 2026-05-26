import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user
from app.db.deps import get_db
from app.models.availability_block import AvailabilityBlock
from app.models.availability_rule import AvailabilityRule
from app.schemas.availability import (
    AvailabilityBlockCreate,
    AvailabilityBlockRead,
    AvailabilityRuleRead,
    AvailabilityRuleUpsert,
)

router = APIRouter(prefix="/availability")


def _rule_to_payload(rule: AvailabilityRule) -> dict:
    return {
        "id": str(rule.id),
        "timezone": rule.timezone,
        "weekly_hours": rule.weekly_hours,
        "created_at": rule.created_at,
        "updated_at": rule.updated_at,
    }


def _block_to_payload(block: AvailabilityBlock) -> dict:
    return {
        "id": str(block.id),
        "start_at": block.start_at,
        "end_at": block.end_at,
        "type": block.type,
        "created_at": block.created_at,
    }


@router.get("/rules")
def list_rules(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    rules = (
        db.execute(
            select(AvailabilityRule).where(AvailabilityRule.user_id == current_user.user_id)
        )
        .scalars()
        .all()
    )
    return {"rules": [AvailabilityRuleRead(**_rule_to_payload(rule)).model_dump() for rule in rules]}


@router.put("/rules")
def upsert_rule(
    payload: AvailabilityRuleUpsert,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Replace the organizer's weekly availability rule (single record per user for MVP)."""
    existing = (
        db.execute(
            select(AvailabilityRule).where(AvailabilityRule.user_id == current_user.user_id)
        )
        .scalars()
        .first()
    )
    serialized = payload.weekly_hours.model_dump()
    if existing is None:
        existing = AvailabilityRule(
            user_id=current_user.user_id,
            timezone=payload.timezone,
            weekly_hours=serialized,
        )
        db.add(existing)
    else:
        existing.timezone = payload.timezone
        existing.weekly_hours = serialized
    db.commit()
    db.refresh(existing)
    return AvailabilityRuleRead(**_rule_to_payload(existing)).model_dump()


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(
    rule_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    rule = db.get(AvailabilityRule, rule_id)
    if not rule or rule.user_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
    db.delete(rule)
    db.commit()
    return None


@router.get("/blocks")
def list_blocks(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    blocks = (
        db.execute(
            select(AvailabilityBlock)
            .where(AvailabilityBlock.user_id == current_user.user_id)
            .order_by(AvailabilityBlock.start_at)
        )
        .scalars()
        .all()
    )
    return {
        "blocks": [
            AvailabilityBlockRead(**_block_to_payload(block)).model_dump() for block in blocks
        ]
    }


@router.post("/blocks", status_code=status.HTTP_201_CREATED)
def create_block(
    payload: AvailabilityBlockCreate,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    block = AvailabilityBlock(
        user_id=current_user.user_id,
        start_at=payload.start_at,
        end_at=payload.end_at,
        type=payload.type,
    )
    db.add(block)
    db.commit()
    db.refresh(block)
    return AvailabilityBlockRead(**_block_to_payload(block)).model_dump()


@router.delete("/blocks/{block_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_block(
    block_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
):
    block = db.get(AvailabilityBlock, block_id)
    if not block or block.user_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Block not found")
    db.delete(block)
    db.commit()
    return None
