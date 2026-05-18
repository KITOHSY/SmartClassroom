import { createBrowserRouter, Navigate } from 'react-router-dom';
import { Layout } from '@/components/Layout';
import { RequireAuth } from '@/components/RequireAuth';
import { AvailableHostsPage } from '@/pages/AvailableHostsPage';
import { CalendarPage } from '@/pages/CalendarPage';
import { LoginPage } from '@/pages/LoginPage';
import { MyReservationsPage } from '@/pages/MyReservationsPage';
import { NotFoundPage } from '@/pages/NotFoundPage';

export const router = createBrowserRouter([
  {
    path: '/login',
    element: <LoginPage />,
  },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <Layout />,
        children: [
          { path: '/', element: <CalendarPage /> },
          { path: '/connect', element: <AvailableHostsPage /> },
          { path: '/reservations', element: <MyReservationsPage /> },
        ],
      },
    ],
  },
  { path: '/404', element: <NotFoundPage /> },
  { path: '*', element: <Navigate to="/404" replace /> },
]);
