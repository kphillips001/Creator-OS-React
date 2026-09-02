"""Narrow local API for Android device status and mirroring."""

import asyncio

from fastapi import APIRouter, HTTPException

from app.services.android_device_service import AndroidDeviceError, AndroidDeviceService


router = APIRouter(prefix="/api/v1/device/android", tags=["android-device"])
android_device_service = AndroidDeviceService()


@router.get("/status")
async def android_status():
    return (await asyncio.to_thread(android_device_service.status)).to_payload()


@router.post("/mirror", status_code=202)
async def mirror_android_device():
    try:
        return (await asyncio.to_thread(android_device_service.launch_mirror)).to_payload()
    except AndroidDeviceError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/sleep")
async def sleep_android_device():
    try:
        return (await asyncio.to_thread(android_device_service.sleep)).to_payload()
    except AndroidDeviceError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
