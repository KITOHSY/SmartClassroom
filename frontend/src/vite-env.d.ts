/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_AUTH_PROVIDER?: 'mock' | 'cnu_sso';
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
