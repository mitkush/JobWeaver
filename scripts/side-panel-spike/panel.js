async function current() {
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  return tab;
}
async function run(action) {
  try { document.querySelector('#result').textContent = JSON.stringify(await action()); }
  catch (error) { document.querySelector('#result').textContent = JSON.stringify({ error: error.message }); }
}
document.querySelector('#scan').onclick = () => run(async () => {
  const tab = await current();
  const result = await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: () => ({ url: location.href, title: document.title }) });
  return result[0].result;
});
document.querySelector('#grant').onclick = () => run(async () => {
  const tab = await current();
  if (!tab.url) throw new Error('No tab URL access. Click the toolbar icon on the fixture tab first.');
  const url = new URL(tab.url);
  if (!['localhost', '127.0.0.1'].includes(url.hostname) || url.protocol !== 'http:') throw new Error('This spike grants only local fixture sites.');
  return { granted: await chrome.permissions.request({ origins: [`http://${url.hostname}/*`] }) };
});
