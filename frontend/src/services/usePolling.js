import { useEffect, useRef, useState } from "react";

// Calls `fn` now and then every `intervalMs`. Returns { data, error, refresh }.
export function usePolling(fn, intervalMs, deps = []) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  const refresh = async () => {
    try {
      setData(await fnRef.current());
      setError(null);
    } catch (e) {
      setError(e.message);
    }
  };

  useEffect(() => {
    setData(null);
    refresh();
    const id = setInterval(refresh, intervalMs);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { data, error, refresh };
}
