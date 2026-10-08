// Prism's built-in worker listener expects a different JSON protocol. Disable it
// before core initialization; our worker owns loading, requests and cancellation.
(globalThis as unknown as { Prism: { manual: boolean; disableWorkerMessageHandler: boolean } }).Prism = {
  manual: true, disableWorkerMessageHandler: true,
};
