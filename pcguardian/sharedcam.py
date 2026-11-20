"""Read one frame from the webcam in Windows' SHARED READ-ONLY mode.

Windows normally gives the camera to one app at a time. MediaCapture's SharedReadOnly mode
lets Peek watch the stream while another app (Zoom, Teams, Camera) stays in control.
Returns JPEG bytes, or None if unavailable. Windows 10/11 only (pywinrt packages).
"""

import asyncio
import logging

log = logging.getLogger(__name__)


async def _grab(timeout=6.0):
    import numpy as np
    from winrt.windows.graphics.imaging import BitmapAlphaMode, BitmapPixelFormat, SoftwareBitmap
    from winrt.windows.media.capture import (MediaCapture, MediaCaptureInitializationSettings,
                                             MediaCaptureMemoryPreference, MediaCaptureSharingMode,
                                             StreamingCaptureMode)
    from winrt.windows.media.capture.frames import MediaFrameSourceGroup, MediaFrameSourceKind
    from winrt.windows.storage.streams import Buffer

    group = info = None
    for g in await MediaFrameSourceGroup.find_all_async():
        for si in g.source_infos:
            if si.source_kind == MediaFrameSourceKind.COLOR:
                group, info = g, si
                break
        if group:
            break
    if group is None:
        return None

    settings = MediaCaptureInitializationSettings()
    settings.source_group = group
    settings.sharing_mode = MediaCaptureSharingMode.SHARED_READ_ONLY
    settings.memory_preference = MediaCaptureMemoryPreference.CPU
    settings.streaming_capture_mode = StreamingCaptureMode.VIDEO
    mc = MediaCapture()
    await mc.initialize_async(settings)
    try:
        source = mc.frame_sources.lookup(info.id)
        reader = await mc.create_frame_reader_async(source)
        await reader.start_async()
        bmp = None
        waited = 0.0
        frames = 0
        while waited < timeout:
            await asyncio.sleep(0.1)
            waited += 0.1
            frame = reader.try_acquire_latest_frame()
            vf = frame.video_media_frame if frame else None
            sb = vf.software_bitmap if vf else None
            if sb is not None:
                frames += 1
                bmp = sb
                if frames >= 5:          # a few frames in, exposure has settled
                    break
        await reader.stop_async()
        if bmp is None:
            return None
        bmp = SoftwareBitmap.convert(bmp, BitmapPixelFormat.BGRA8, BitmapAlphaMode.PREMULTIPLIED)
        w, h = bmp.pixel_width, bmp.pixel_height
        buf = Buffer(w * h * 4)
        bmp.copy_to_buffer(buf)
        arr = np.frombuffer(memoryview(buf), dtype=np.uint8)[: w * h * 4].reshape(h, w, 4)
        import cv2
        if arr.mean() < 8:
            return None
        ok, jpg = cv2.imencode(".jpg", arr[:, :, :3], [cv2.IMWRITE_JPEG_QUALITY, 85])
        return jpg.tobytes() if ok else None
    finally:
        mc.close()


def grab_jpeg():
    try:
        return asyncio.run(_grab())
    except Exception as exc:
        log.info("Shared-mode camera read failed: %s", exc)
        return None
