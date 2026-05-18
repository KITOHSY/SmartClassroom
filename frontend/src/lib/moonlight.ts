import type { HostConnectionInfo } from '@/api/connect';

export type DetectedOS = 'windows' | 'macos' | 'linux' | 'unknown';

/**
 * moonlight:// 커스텀 URL 조립.
 *
 * T13(moonlight-qt fork)의 커스텀 URL 핸들러 계약 — T13 EXP의 `--connect-token` /
 * `--host-id` 인자에 대응한다. T13 머지 전까지는 이 스키마가 프런트↔클라이언트 계약이다.
 */
export function buildMoonlightUrl(token: string, host: HostConnectionInfo): string {
  const params = new URLSearchParams({
    token,
    'host-id': String(host.id),
    host: host.ip_address ?? '',
    port: String(host.sunshine_port),
  });
  return `moonlight://connect?${params.toString()}`;
}

interface UserAgentData {
  platform?: string;
}

/** 클라이언트 OS 추정 — 설치 가이드 분기용. userAgentData 우선, UA 문자열 fallback. */
export function detectOS(): DetectedOS {
  if (typeof navigator === 'undefined') return 'unknown';
  const uaData = (navigator as Navigator & { userAgentData?: UserAgentData }).userAgentData;
  const platform = (uaData?.platform ?? navigator.userAgent ?? '').toLowerCase();
  if (platform.includes('win')) return 'windows';
  if (platform.includes('mac') || platform.includes('darwin')) return 'macos';
  if (platform.includes('linux') || platform.includes('x11')) return 'linux';
  return 'unknown';
}

/**
 * moonlight:// URL을 실행하고 핸들러 등록 여부를 휴리스틱으로 판정한다.
 *
 * 브라우저에는 커스텀 스킴 핸들러 등록 여부를 동기적으로 확인하는 API가 없다.
 * URL로 이동을 시도한 뒤 `timeoutMs` 안에 페이지가 hidden/blur 되면 OS가 외부 앱으로
 * 전환한 것으로 보고 true(핸들러 동작 추정)를, 그대로면 false(미등록 추정)를 반환한다.
 * — 완벽하지 않은 휴리스틱이며 false라도 실제로는 동작했을 수 있다.
 */
export function launchMoonlight(url: string, timeoutMs = 1800): Promise<boolean> {
  return new Promise<boolean>((resolve) => {
    if (typeof window === 'undefined' || typeof document === 'undefined') {
      resolve(false);
      return;
    }
    let settled = false;
    const finish = (handled: boolean): void => {
      if (settled) return;
      settled = true;
      document.removeEventListener('visibilitychange', onVisibility);
      window.removeEventListener('blur', onBlur);
      window.clearTimeout(timer);
      resolve(handled);
    };
    const onVisibility = (): void => {
      if (document.visibilityState === 'hidden') finish(true);
    };
    const onBlur = (): void => finish(true);
    const timer = window.setTimeout(() => finish(false), timeoutMs);
    document.addEventListener('visibilitychange', onVisibility);
    window.addEventListener('blur', onBlur);
    try {
      window.location.href = url;
    } catch {
      // 일부 환경(jsdom 등)은 커스텀 스킴 네비게이션을 막는다 — 휴리스틱은 그대로 진행.
    }
  });
}
