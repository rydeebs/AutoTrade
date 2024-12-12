const DropdownMenu = ({ children }) => {
  const [isOpen, setIsOpen] = React.useState(false);
  
  return React.createElement('div', {
    className: 'relative inline-block text-left'
  }, children(isOpen, setIsOpen));
};

const DropdownMenuTrigger = ({ children, asChild }) => {
  return children;
};

const DropdownMenuContent = ({ children, align = "center", className = "" }) => {
  return React.createElement('div', {
    className: `absolute right-0 mt-2 w-56 origin-top-right rounded-md bg-black border border-white/10 shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none ${className}`
  }, children);
};

const DropdownMenuItem = ({ children, className = "" }) => {
  return React.createElement('button', {
    className: `block w-full px-4 py-2 text-sm text-white hover:bg-white/5 ${className}`
  }, children);
};

window.DropdownMenu = DropdownMenu;
window.DropdownMenuTrigger = DropdownMenuTrigger;
window.DropdownMenuContent = DropdownMenuContent;
window.DropdownMenuItem = DropdownMenuItem; 