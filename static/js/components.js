window.Components = {
    // Basic card components
    Card: function(props) {
        return React.createElement('div', {
            className: `bg-black border border-white/10 rounded-lg p-6 ${props.className || ''}`,
            ...props
        }, props.children);
    },

    CardHeader: function(props) {
        return React.createElement('div', {
            className: `flex flex-row items-center justify-between pb-2 ${props.className || ''}`,
            ...props
        }, props.children);
    },

    CardTitle: function(props) {
        return React.createElement('h3', {
            className: `text-xl font-bold ${props.className || ''}`,
            ...props
        }, props.children);
    },

    CardContent: function(props) {
        return React.createElement('div', {
            className: `space-y-4 ${props.className || ''}`,
            ...props
        }, props.children);
    },

    // Button component
    Button: function(props) {
        return React.createElement('button', {
            className: `inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors 
                       focus:outline-none disabled:opacity-50 ${props.className || ''}`,
            ...props
        }, props.children);
    },

    // Badge component
    Badge: function(props) {
        return React.createElement('span', {
            className: `inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${props.className || ''}`,
            ...props
        }, props.children);
    },

    // Dropdown components
    DropdownMenu: function(props) {
        const [isOpen, setIsOpen] = React.useState(false);
        return props.children(isOpen, setIsOpen);
    },

    DropdownMenuTrigger: function(props) {
        return React.createElement('div', {
            onClick: (e) => {
                e.stopPropagation();
                if (props.onClick) props.onClick(e);
            },
            ...props
        }, props.children);
    },

    DropdownMenuContent: function(props) {
        return React.createElement('div', {
            className: `absolute z-50 min-w-[8rem] rounded-md border border-white/10 bg-black p-1 shadow-md ${props.className || ''}`,
            ...props
        }, props.children);
    },

    DropdownMenuItem: function(props) {
        return React.createElement('button', {
            className: `relative flex w-full select-none items-center rounded-sm px-2 py-1.5 text-sm outline-none hover:bg-white/10 ${props.className || ''}`,
            ...props
        }, props.children);
    }
};