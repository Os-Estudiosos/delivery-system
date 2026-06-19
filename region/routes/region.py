import os
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database.connection import get_session
from database.models import Region

router = APIRouter(prefix='/region', tags=['region'])

# Dynamic environment values for the mock
REGION_ID = int(os.environ.get("REGION_ID", "1"))
CITY_NAME = os.environ.get("CITY_NAME", "São Paulo, Brazil")

class RegionCreate(BaseModel):
    name: str


class RegionResponse(BaseModel):
    id: int
    name: str


@router.get('/', tags=['get regions'])
def get_regions(session: Session = Depends(get_session)):
    # DUMMY MOCK FOR PERFORMANCE DIAGNOSTICS:
    return [RegionResponse(id=REGION_ID, name=CITY_NAME)]
    # regions = session.query(Region).all()
    # return [RegionResponse(id=region.id, name=region.name) for region in regions]


@router.get('/{region_id}', tags=['get region by id'])
def get_region(region_id: int, session: Session = Depends(get_session)):
    # DUMMY MOCK FOR PERFORMANCE DIAGNOSTICS:
    return RegionResponse(id=region_id, name=CITY_NAME)
    # region = session.query(Region).filter(Region.id == region_id).first()
    # if not region:
    #     raise HTTPException(
    #         status_code=status.HTTP_404_NOT_FOUND,
    #         detail='region not found.',
    #     )
    # return RegionResponse(id=region.id, name=region.name)


@router.post('/', tags=['create region'], status_code=status.HTTP_201_CREATED)
def create_region(region: RegionCreate, session: Session = Depends(get_session)):
    # DUMMY MOCK FOR PERFORMANCE DIAGNOSTICS:
    return RegionResponse(id=1, name=region.name)
    # db_region = Region(
    #     name=region.name,
    # )
    # session.add(db_region)
    # try:
    #     session.commit()
    # except IntegrityError:
    #     session.rollback()
    #     raise HTTPException(
    #         status_code=status.HTTP_409_CONFLICT,
    #         detail='region already exists or payload violates constraints.',
    #     )
    # session.refresh(db_region)
    # return RegionResponse(
    #     id=db_region.id,
    #     name=db_region.name,
    # )


@router.patch('/{region_id}', tags=['update region'])
def update_region(region_id: int, region: RegionCreate, session: Session = Depends(get_session)):
    db_region = session.query(Region).filter(Region.id == region_id).first()
    if not db_region:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='region not found.',
        )

    db_region.name = region.name

    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='region already exists or payload violates constraints.',
        )

    session.refresh(db_region)

    return RegionResponse(
        id=db_region.id,
        name=db_region.name,
    )


@router.delete('/{region_id}', status_code=status.HTTP_204_NO_CONTENT, tags=['delete region'])
def delete_region(region_id: int, session: Session = Depends(get_session)):
    db_region = session.query(Region).filter(Region.id == region_id).first()
    if not db_region:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='region not found.',
        )
    session.delete(db_region)
    session.commit()