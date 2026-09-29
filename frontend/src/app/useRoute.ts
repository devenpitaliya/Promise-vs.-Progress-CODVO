import { useCallback, useEffect, useState } from 'react';

const ROUTES = ['meetings', 'commitments', 'reconciliation', 'settings'] as const;
export type Route = (typeof ROUTES)[number];

function parse(pathname: string): Route {
  const segment = pathname.replace(/^\/+/, '').split('/')[0] as Route;
  return ROUTES.includes(segment) ? segment : 'meetings';
}

/** Minimal path-based routing (/meetings, /commitments, ...) with back/forward support. */
export function useRoute(): [Route, (route: Route) => void] {
  const [route, setRoute] = useState<Route>(() => parse(window.location.pathname));

  useEffect(() => {
    const onPop = () => setRoute(parse(window.location.pathname));
    window.addEventListener('popstate', onPop);
    if (window.location.pathname !== `/${route}`) window.history.replaceState(null, '', `/${route}`);
    return () => window.removeEventListener('popstate', onPop);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- normalise the URL once on mount
  }, []);

  const navigate = useCallback((next: Route) => {
    setRoute(next);
    if (window.location.pathname !== `/${next}`) window.history.pushState(null, '', `/${next}`);
  }, []);

  return [route, navigate];
}
