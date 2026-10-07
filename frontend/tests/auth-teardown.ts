export default async function teardown() {
  const response = await fetch('http://127.0.0.1:18003/testing/cleanup', {
    method: 'POST', signal: AbortSignal.timeout(15_000),
  });
  if (!response.ok) throw new Error(`Auth test database cleanup failed (${response.status}).`);
}
