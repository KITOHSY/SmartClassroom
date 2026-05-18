import { useCallback, useState } from 'react';
import type { ConnectTokenResponse } from '@/api/connect';
import { buildMoonlightUrl, launchMoonlight } from '@/lib/moonlight';

export interface MoonlightConnect {
  /** ConnectTokenResponse를 받아 moonlight://를 실행. 핸들러 미등록 추정 시 설치 가이드를 연다. */
  launch: (token: ConnectTokenResponse) => Promise<void>;
  guideOpen: boolean;
  closeGuide: () => void;
}

/**
 * connect 토큰 → moonlight:// 실행 흐름을 공유하는 훅.
 * Section A(예약 카드 [접속])와 Section B(가용 PC [즉시 사용])가 함께 쓴다.
 */
export function useMoonlightConnect(): MoonlightConnect {
  const [guideOpen, setGuideOpen] = useState(false);

  const launch = useCallback(async (token: ConnectTokenResponse): Promise<void> => {
    const url = buildMoonlightUrl(token.token, token.host);
    const handled = await launchMoonlight(url);
    if (!handled) setGuideOpen(true);
  }, []);

  const closeGuide = useCallback(() => setGuideOpen(false), []);

  return { launch, guideOpen, closeGuide };
}
