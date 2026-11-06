(() => {
  const stack = document.createElement('section');
  stack.className = 'notification-stack';
  stack.setAttribute('aria-label', 'Notifications');
  document.body.appendChild(stack);

  window.showNotification = ({ message, type = 'info', title = '' }) => {
    const item = document.createElement('article');
    item.className = `notification notification-${type}`;
    item.setAttribute('role', type === 'error' ? 'alert' : 'status');

    const copy = document.createElement('div');
    const heading = document.createElement('strong');
    heading.textContent = title || (type === 'error' ? 'Something went wrong' : 'Double Trouble');
    const detail = document.createElement('p');
    detail.textContent = String(message);
    copy.append(heading, detail);

    const close = document.createElement('button');
    close.type = 'button';
    close.setAttribute('aria-label', 'Dismiss notification');
    close.textContent = '×';
    close.addEventListener('click', () => item.remove());
    item.append(copy, close);
    stack.appendChild(item);

    const timeout = window.setTimeout(() => item.remove(), type === 'error' ? 9000 : 6000);
    item.addEventListener('mouseenter', () => window.clearTimeout(timeout), { once: true });
    return item;
  };
})();
