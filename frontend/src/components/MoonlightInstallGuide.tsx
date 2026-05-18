import { useEffect, type ReactElement } from 'react';
import { detectOS, type DetectedOS } from '@/lib/moonlight';

// T20 산출물 — 정식 인스톨러 배포 채널이 생기면 이 URL을 교체한다(moonlight:// 핸들러 자동 등록 포함).
// 그 전까지는 moonlight-qt 공식 릴리스로 안내한다.
const MOONLIGHT_RELEASES_URL = 'https://github.com/moonlight-stream/moonlight-qt/releases';

const OS_LABEL: Record<DetectedOS, string> = {
  windows: 'Windows',
  macos: 'macOS',
  linux: 'Linux',
  unknown: '사용 중인 OS',
};

interface Props {
  open: boolean;
  onClose: () => void;
}

/**
 * moonlight:// 핸들러가 동작하지 않은 것으로 추정될 때 노출하는 설치 안내 패널.
 * 핸들러 동작 여부는 동기적으로 알 수 없어 휴리스틱(launchMoonlight)으로 판정하므로,
 * 이미 설치된 사용자에게도 뜰 수 있다 — 안내문에 "이미 설치돼 있다면 다시 시도" 문구를 둔다.
 */
export function MoonlightInstallGuide({ open, onClose }: Props): ReactElement | null {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;
  const os = detectOS();

  return (
    <div
      className="fixed inset-0 z-40 flex items-center justify-center bg-slate-900/40 p-4"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="moonlight-guide-title"
        className="w-full max-w-md space-y-4 rounded-lg border border-slate-200 bg-white p-6 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="moonlight-guide-title" className="text-lg font-semibold text-slate-900">
          Moonlight 앱이 필요해요
        </h2>
        <p className="text-sm text-slate-600">
          접속하려면 {OS_LABEL[os]}용 Moonlight 클라이언트가 설치되어 있어야 합니다. 이미 설치돼
          있다면 브라우저의 앱 실행 허용을 확인한 뒤 같은 버튼으로 다시 시도해 주세요. 발급된
          접속 토큰은 예약 종료 시각까지 유효합니다.
        </p>
        <div className="flex items-center justify-between">
          <a
            href={MOONLIGHT_RELEASES_URL}
            target="_blank"
            rel="noreferrer"
            className="rounded bg-brand px-3 py-2 text-sm font-medium text-white hover:opacity-90"
          >
            Moonlight 다운로드
          </a>
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-slate-300 px-3 py-2 text-sm text-slate-700 hover:bg-slate-100"
          >
            닫기
          </button>
        </div>
      </div>
    </div>
  );
}
