import { type ReactElement } from 'react';
import { Link } from 'react-router-dom';

export function NotFoundPage(): ReactElement {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-3 text-center">
      <h1 className="text-3xl font-semibold text-slate-900">404</h1>
      <p className="text-slate-600">요청한 페이지를 찾을 수 없습니다.</p>
      <Link to="/" className="text-sm text-brand underline">
        캘린더로 이동
      </Link>
    </div>
  );
}
