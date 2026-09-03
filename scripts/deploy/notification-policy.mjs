/** Preserve unrelated routes while keeping both Sicurre services deliverable. */
export function withOperationsRoutes(policy, receiver) {
  const matchers = [["stack", "=", "sicurre"], ["service", "=", "sicurre-ml"]];
  const managed = (route) => route.object_matchers?.length === 1
    && matchers.some((matcher) => JSON.stringify(route.object_matchers[0]) === JSON.stringify(matcher));
  const routes = matchers.map((matcher) => {
    const existing = (policy.routes || []).find((route) => managed(route)
      && JSON.stringify(route.object_matchers[0]) === JSON.stringify(matcher));
    const children = (existing?.routes || []).filter((route) => ![
      [["alertname", "=", "Sicurre controlled operational exercise"]],
      [["exercise", "=", "synthetic"]],
    ].some((match) => JSON.stringify(route.object_matchers) === JSON.stringify(match)));
    return {
      ...existing,
      receiver,
      object_matchers: [matcher],
      group_by: ["grafana_folder", "alertname"],
      group_wait: "30s",
      group_interval: "5m",
      repeat_interval: "4h",
      ...(matcher[0] === "stack" ? {
        routes: [{
          receiver,
          object_matchers: [["exercise", "=", "synthetic"]],
          group_wait: "30s",
          group_interval: "1m",
          repeat_interval: "4h",
        }, ...children],
      } : {}),
    };
  });
  return { ...policy, routes: [...routes, ...(policy.routes || []).filter((route) => !managed(route))] };
}
