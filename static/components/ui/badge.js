const Badge = ({ children, className = "", variant = "default" }) => {
  const baseStyles = "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2";
  
  const variants = {
    default: "border-transparent bg-primary text-primary-foreground hover:bg-primary/80",
    outline: "border border-white/10",
  };

  return React.createElement('div', {
    className: `${baseStyles} ${variants[variant]} ${className}`
  }, children);
};

window.Badge = Badge; 