import { describe, it, expect, afterEach } from 'vitest';
import { buildMoonlightUrl, detectOS } from '@/lib/moonlight';
import type { HostConnectionInfo } from '@/api/connect';

describe('buildMoonlightUrl', () => {
  it('token/host-id/host/port 쿼리를 담은 moonlight:// URL을 만든다', () => {
    const host: HostConnectionInfo = {
      id: 7,
      hostname: 'pc-7',
      ip_address: '10.0.0.7',
      sunshine_port: 47989,
    };
    const url = buildMoonlightUrl('raw-token-abc', host);
    expect(url.startsWith('moonlight://connect?')).toBe(true);

    const params = new URLSearchParams(url.split('?')[1]);
    expect(params.get('token')).toBe('raw-token-abc');
    expect(params.get('host-id')).toBe('7');
    expect(params.get('host')).toBe('10.0.0.7');
    expect(params.get('port')).toBe('47989');
  });

  it('ip_address가 null이면 host 파라미터는 빈 문자열', () => {
    const host: HostConnectionInfo = {
      id: 1,
      hostname: 'pc-1',
      ip_address: null,
      sunshine_port: 47989,
    };
    const params = new URLSearchParams(buildMoonlightUrl('t', host).split('?')[1]);
    expect(params.get('host')).toBe('');
  });

  it('broker 파라미터에 현재 페이지 origin을 담는다 (T14)', () => {
    const host: HostConnectionInfo = {
      id: 7,
      hostname: 'pc-7',
      ip_address: '10.0.0.7',
      sunshine_port: 47989,
    };
    const params = new URLSearchParams(buildMoonlightUrl('t', host).split('?')[1]);
    expect(params.get('broker')).toBe(window.location.origin);
  });
});

describe('detectOS', () => {
  afterEach(() => {
    Reflect.deleteProperty(navigator, 'userAgentData');
  });

  it('알려진 OS 값 중 하나를 반환한다', () => {
    expect(['windows', 'macos', 'linux', 'unknown']).toContain(detectOS());
  });

  it('userAgentData.platform이 Windows면 windows', () => {
    Object.defineProperty(navigator, 'userAgentData', {
      value: { platform: 'Windows' },
      configurable: true,
    });
    expect(detectOS()).toBe('windows');
  });

  it('userAgentData.platform이 macOS면 macos', () => {
    Object.defineProperty(navigator, 'userAgentData', {
      value: { platform: 'macOS' },
      configurable: true,
    });
    expect(detectOS()).toBe('macos');
  });
});
