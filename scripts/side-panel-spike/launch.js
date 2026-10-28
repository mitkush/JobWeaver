document.querySelector('#open').onclick = async () => {
  try {
    const tabId = Number(new URL(location.href).searchParams.get('tab'));
    await chrome.sidePanel.open({ tabId });
    document.querySelector('#result').textContent = 'Opened';
  } catch (error) { document.querySelector('#result').textContent = error.message; }
};
