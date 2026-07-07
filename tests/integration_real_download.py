"""실제 네트워크를 사용하는 통합 검증 스크립트 (pytest 자동 수집 대상 아님).

아주 짧은(19초) 공개 테스트 영상 하나를 실제로 내려받아
yt-dlp + ffmpeg 파이프라인이 끝까지 동작하는지 확인한다.
자막 다운로드 등은 포함하지 않으며, 개발/검증 목적의 1회성 실행이다.
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.downloader import DownloadError, download_item, fetch_video_info  # noqa: E402
from app.models import DownloadStatus, MediaFormat, QueueItem, Quality  # noqa: E402

TEST_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"  # "Me at the zoo" - 최초 유튜브 업로드 영상, 19초


def main() -> int:
    tmp_dir = tempfile.mkdtemp(prefix="ytdl_test_")
    print(f"임시 저장 경로: {tmp_dir}")
    ok = True

    try:
        print("\n=== 1) 메타데이터 조회 ===")
        video = fetch_video_info(TEST_URL)
        print(f"제목: {video.title}")
        print(f"길이: {video.duration}s")
        print(f"업로더: {video.uploader}")
        assert video.id == "jNQXAC9IVRw"

        print("\n=== 2) 영상(mp4, 최저화질) 다운로드 ===")
        progress_log = []
        video_item = QueueItem(video=video, media_format=MediaFormat.VIDEO, quality=Quality.WORST, output_dir=tmp_dir)
        download_item(video_item, progress_callback=lambda i: progress_log.append(i.progress))
        assert video_item.status == DownloadStatus.COMPLETED
        assert video_item.output_path and os.path.exists(video_item.output_path)
        size = os.path.getsize(video_item.output_path)
        print(f"결과 파일: {video_item.output_path} ({size} bytes)")
        assert size > 1000, "다운로드된 파일 크기가 비정상적으로 작음"
        assert len(progress_log) > 0, "progress_callback이 한 번도 호출되지 않음"
        print("[OK] 영상 다운로드 성공")

        print("\n=== 3) 오디오(mp3) 다운로드 ===")
        audio_item = QueueItem(video=video, media_format=MediaFormat.AUDIO, quality=Quality.BEST, output_dir=tmp_dir)
        download_item(audio_item)
        assert audio_item.status == DownloadStatus.COMPLETED
        assert audio_item.output_path
        # FFmpegExtractAudio 후처리 후 실제 파일 확장자는 mp3로 바뀜
        mp3_candidates = [f for f in os.listdir(tmp_dir) if f.lower().endswith(".mp3")]
        assert mp3_candidates, f"mp3 파일을 찾을 수 없음. 디렉터리 내용: {os.listdir(tmp_dir)}"
        mp3_path = os.path.join(tmp_dir, mp3_candidates[0])
        mp3_size = os.path.getsize(mp3_path)
        print(f"결과 파일: {mp3_path} ({mp3_size} bytes)")
        assert mp3_size > 1000
        print("[OK] 오디오 추출 성공")

        print("\n=== 4) 실패 케이스 (잘못된 video id) ===")
        from app.models import VideoInfo

        bad_video = VideoInfo(id="invalid_id_zzz", title="bad", url="https://www.youtube.com/watch?v=invalid_id_zzz")
        bad_item = QueueItem(video=bad_video, output_dir=tmp_dir)
        try:
            download_item(bad_item)
            print("[FAIL] 잘못된 URL인데 예외가 발생하지 않음")
            ok = False
        except DownloadError:
            assert bad_item.status == DownloadStatus.FAILED
            print("[OK] 잘못된 URL에 대해 DownloadError 발생 및 상태 FAILED 반영 확인")

    except AssertionError as e:
        import traceback

        traceback.print_exc()
        print(f"[FAIL] {e}")
        ok = False
    except Exception as e:
        import traceback

        traceback.print_exc()
        print(f"[FAIL] 예상치 못한 예외: {e!r}")
        ok = False
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        print(f"\n임시 디렉터리 정리 완료: {tmp_dir}")

    print("\n" + ("ALL INTEGRATION CHECKS PASSED" if ok else "INTEGRATION CHECKS FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
