window.Icons = {
  ArrowUp: function(props) {
      return React.createElement('svg', {
          viewBox: "0 0 24 24",
          fill: "none",
          stroke: "currentColor",
          strokeWidth: "2",
          strokeLinecap: "round",
          strokeLinejoin: "round",
          className: props.className || ''
      }, React.createElement('path', { d: "m5 12 7-7 7 7M12 19V5" }));
  },

  ArrowDown: function(props) {
      return React.createElement('svg', {
          viewBox: "0 0 24 24",
          fill: "none",
          stroke: "currentColor",
          strokeWidth: "2",
          strokeLinecap: "round",
          strokeLinejoin: "round",
          className: props.className || ''
      }, React.createElement('path', { d: "M19 12l-7 7-7-7M12 5v14" }));
  },

  Power: function(props) {
      return React.createElement('svg', {
          viewBox: "0 0 24 24",
          fill: "none",
          stroke: "currentColor",
          strokeWidth: "2",
          strokeLinecap: "round",
          strokeLinejoin: "round",
          className: props.className || ''
      }, [
          React.createElement('path', { key: 1, d: "M18.36 6.64A9 9 0 0 1 20.77 15" }),
          React.createElement('path', { key: 2, d: "M6.16 6.16a9 9 0 1 0 12.68 12.68" }),
          React.createElement('path', { key: 3, d: "M12 2v4" })
      ]);
  },

  RefreshCcw: function(props) {
      return React.createElement('svg', {
          viewBox: "0 0 24 24",
          fill: "none",
          stroke: "currentColor",
          strokeWidth: "2",
          strokeLinecap: "round",
          strokeLinejoin: "round",
          className: props.className || ''
      }, [
          React.createElement('path', { key: 1, d: "M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" }),
          React.createElement('path', { key: 2, d: "M3 3v5h5" }),
          React.createElement('path', { key: 3, d: "M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16" }),
          React.createElement('path', { key: 4, d: "M16 21h5v-5" })
      ]);
  },

  MoreHorizontal: function(props) {
      return React.createElement('svg', {
          viewBox: "0 0 24 24",
          fill: "none",
          stroke: "currentColor",
          strokeWidth: "2",
          strokeLinecap: "round",
          strokeLinejoin: "round",
          className: props.className || ''
      }, [
          React.createElement('circle', { key: 1, cx: "12", cy: "12", r: "1" }),
          React.createElement('circle', { key: 2, cx: "19", cy: "12", r: "1" }),
          React.createElement('circle', { key: 3, cx: "5", cy: "12", r: "1" })
      ]);
  }
};