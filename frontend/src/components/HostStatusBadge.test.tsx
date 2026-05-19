import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { HostStatusBadge } from './HostStatusBadge';

describe('<HostStatusBadge />', () => {
  it.each([
    ['IDLE', '대기 중'],
    ['IN_USE', '사용 중'],
    ['DEGRADED', '점검 중'],
    ['OFFLINE', '오프라인'],
  ])('status=%s → 라벨 "%s"', (status, label) => {
    render(<HostStatusBadge status={status} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it('알 수 없는 status → "알 수 없음" fallback', () => {
    render(<HostStatusBadge status="ACTIVE" />);
    expect(screen.getByText('알 수 없음')).toBeInTheDocument();
  });
});
