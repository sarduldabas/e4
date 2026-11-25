// Demo | Live. Demo = the built-in sample data (nothing leaves the browser). Live = the real backend and agents.
import { useCallback, useEffect, useState } from 'react';

const KEY = 'coe4.mode';
const read = () => { try { return localStorage.getItem(KEY) === 'live' ? 'live' : 'demo'; } catch { return 'demo'; } };

export function useMode() {
  const [mode, setModeState] = useState(read);
  const setMode = useCallback((m) => {
    setModeState(m);
    try { localStorage.setItem(KEY, m); } catch { /* private mode: the choice just is not remembered */ }
  }, []);
  useEffect(() => { document.documentElement.dataset.mode = mode; }, [mode]);
  return [mode, setMode];
}
