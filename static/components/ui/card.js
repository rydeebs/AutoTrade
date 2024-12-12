const Card = ({ children, className = "" }) => {
  return React.createElement('div', {
    className: `rounded-lg border border-white/10 bg-black text-white ${className}`
  }, children);
};

const CardHeader = ({ children, className = "" }) => {
  return React.createElement('div', {
    className: `flex flex-col space-y-1.5 p-6 items-start ${className}`
  }, children);
};

const CardTitle = ({ children, className = "" }) => {
  return React.createElement('h3', {
    className: `text-2xl font-semibold leading-none tracking-tight ${className}`
  }, children);
};

const CardContent = ({ children, className = "" }) => {
  return React.createElement('div', {
    className: `p-6 pt-0 ${className}`
  }, children);
};

window.Card = Card;
window.CardHeader = CardHeader;
window.CardTitle = CardTitle;
window.CardContent = CardContent; 