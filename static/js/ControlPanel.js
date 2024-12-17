window.ControlPanel = function() {
    const [isLoading, setIsLoading] = React.useState(true);
    const [error, setError] = React.useState(null);
    
    // Initialize states with default values
    const [status, setStatus] = React.useState({
        is_trading_hours: false,
        strategy_running: false,
        current_time: new Date().toLocaleString()
    });
    
    const [performanceMetrics, setPerformanceMetrics] = React.useState({
        wow: { percentage: 0, dollars: 0 },
        mom: { percentage: 0, dollars: 0 },
        trades: { won: 0, lost: 0 }
    });
    
    const [positions, setPositions] = React.useState([]);
    const [trades, setTrades] = React.useState([]);
    const [account, setAccount] = React.useState({
        equity: 0,
        buying_power: 0,
        cash: 0
    });

    // Separate data fetching functions for better control
    const fetchStatus = async () => {
        const response = await fetch('/api/status');
        if (!response.ok) throw new Error(`Status API error: ${response.status}`);
        return response.json();
    };

    const fetchPerformanceMetrics = async () => {
        try {
            const response = await fetch('/api/performance_metrics');
            if (!response.ok) throw new Error(`Metrics API error: ${response.status}`);
            const data = await response.json();
            console.log('Raw performance metrics data:', data); // Debug log
            return data;
        } catch (error) {
            console.error('Error fetching metrics:', error);
            throw error;
        }
    };

    const fetchPositions = async () => {
        const response = await fetch('/api/positions');
        if (!response.ok) throw new Error(`Positions API error: ${response.status}`);
        return response.json();
    };

    const fetchTrades = async () => {
        const response = await fetch('/api/trades');
        if (!response.ok) throw new Error(`Trades API error: ${response.status}`);
        return response.json();
    };

    const fetchAccount = async () => {
        const response = await fetch('/api/account');
        if (!response.ok) throw new Error(`Account API error: ${response.status}`);
        return response.json();
    };

    const fetchAllData = async () => {
        try {
            console.log('Fetching all data...'); // Debug log
            const [
                statusData,
                metricsData,
                positionsData,
                tradesData,
                accountData
            ] = await Promise.all([
                fetchStatus(),
                fetchPerformanceMetrics(),
                fetchPositions(),
                fetchTrades(),
                fetchAccount()
            ]);

            setStatus(statusData);
            setPerformanceMetrics(metricsData);
            setPositions(positionsData.positions || []);
            setTrades(tradesData.trades || []);
            setAccount(accountData);
            setError(null);
            setIsLoading(false);

            console.log('Data update complete:', {
                metrics: metricsData,
                positions: positionsData.positions,
                trades: tradesData.trades
            }); // Debug log
        } catch (error) {
            console.error('Error fetching data:', error);
            setError(error.message);
            setIsLoading(false);
        }
    };

    // Effect for initial data load and polling
    React.useEffect(() => {
        let isMounted = true;
        let intervalId = null;

        const initializeData = async () => {
            if (isMounted) {
                await fetchAllData();
            }
        };

        initializeData();

        // Set up polling - more frequent updates when strategy is running
        intervalId = setInterval(() => {
            if (isMounted) {
                fetchAllData();
            }
        }, 5000); // Poll every 5 seconds

        return () => {
            isMounted = false;
            if (intervalId) {
                clearInterval(intervalId);
            }
        };
    }, []); // Empty dependency array for initial setup

    // Additional effect specifically for strategy running state
    React.useEffect(() => {
        let intervalId = null;

        if (status.strategy_running) {
            // More frequent updates when strategy is running
            intervalId = setInterval(fetchAllData, 2000); // Poll every 2 seconds when running
        }

        return () => {
            if (intervalId) {
                clearInterval(intervalId);
            }
        };
    }, [status.strategy_running]);

    const handleStartStrategy = async () => {
        try {
            const response = await fetch('/api/start', {
                method: 'POST'
            });
            
            if (!response.ok) {
                throw new Error(`Failed to start strategy: ${response.status}`);
            }
            
            await fetchAllData(); // Immediately fetch new data after starting
            setStatus(prev => ({
                ...prev,
                strategy_running: true
            }));
        } catch (error) {
            console.error('Error starting strategy:', error);
            setError(error.message);
        }
    };

    const handleStopStrategy = async () => {
        try {
            const response = await fetch('/api/stop', {
                method: 'POST'
            });
            
            if (!response.ok) {
                throw new Error(`Failed to stop strategy: ${response.status}`);
            }
            
            await fetchAllData(); // Immediately fetch new data after stopping
            setStatus(prev => ({
                ...prev,
                strategy_running: false
            }));
        } catch (error) {
            console.error('Error stopping strategy:', error);
            setError(error.message);
        }
    };

    const handleClosePosition = async (symbol) => {
        if (!status.strategy_running) return;
        
        try {
            const response = await fetch(`/api/close_position/${symbol}`, {
                method: 'POST'
            });
            if (response.ok) {
                await fetchAllData(); // Refresh all data after closing position
            }
        } catch (error) {
            console.error('Error closing position:', error);
        }
    };

    // Main render
    return React.createElement('div', {
        className: 'min-h-screen bg-black p-6 text-white'
    }, 
        isLoading ? React.createElement('div', {
            className: 'flex items-center justify-center h-screen'
        }, 'Loading dashboard...') :
        error ? React.createElement('div', {
            className: 'flex items-center justify-center h-screen text-red-500'
        }, 'Error: ' + error) :
        React.createElement('div', {
            className: 'mx-auto max-w-7xl space-y-6'
        }, [
            // System Status Card
            React.createElement('div', {
                key: 'system-status',
                className: 'bg-gray-800 rounded-lg p-6 space-y-4'
            }, [
                React.createElement('h2', {
                    className: 'text-xl font-bold'
                }, 'System Status'),
                React.createElement('div', {
                    className: 'grid gap-4'
                }, [
                    // Market Status
                    React.createElement('div', {
                        className: 'flex items-center justify-between'
                    }, [
                        React.createElement('span', {
                            className: 'text-gray-400'
                        }, 'Market Status'),
                        React.createElement('span', {
                            className: status.is_trading_hours ? 'text-green-500' : 'text-red-500'
                        }, status.is_trading_hours ? 'Market Open' : 'Market Closed')
                    ]),
                    // Strategy Status
                    React.createElement('div', {
                        className: 'flex items-center justify-between'
                    }, [
                        React.createElement('span', {
                            className: 'text-gray-400'
                        }, 'Strategy Running'),
                        React.createElement('span', {
                            className: 'font-bold'
                        }, status.strategy_running ? 'Yes' : 'No')
                    ]),
                    // Current Time
                    React.createElement('div', {
                        className: 'flex items-center justify-between'
                    }, [
                        React.createElement('span', {
                            className: 'text-gray-400'
                        }, 'Current Time'),
                        React.createElement('span', {
                            className: 'font-mono'
                        }, status.current_time)
                    ]),
                    // Control Buttons
                    React.createElement('div', {
                        className: 'flex justify-end space-x-2'
                    }, [
                        React.createElement('button', {
                            className: `bg-green-500 text-white px-4 py-2 rounded ${status.strategy_running ? 'opacity-50 cursor-not-allowed' : ''}`,
                            onClick: handleStartStrategy,
                            disabled: status.strategy_running
                        }, 'Start Strategy'),
                        React.createElement('button', {
                            className: `bg-red-500 text-white px-4 py-2 rounded ${!status.strategy_running ? 'opacity-50 cursor-not-allowed' : ''}`,
                            onClick: handleStopStrategy,
                            disabled: !status.strategy_running
                        }, 'Stop Strategy')
                    ])
                ])
            ]),

            // Account Overview Card
            React.createElement('div', {
                key: 'account-overview',
                className: 'bg-gray-800 rounded-lg p-6 space-y-4'
            }, [
                React.createElement('h2', {
                    className: 'text-xl font-bold'
                }, 'Account Overview'),
                React.createElement('div', {
                    className: 'grid grid-cols-3 gap-6'
                }, [
                    React.createElement('div', {
                        className: 'space-y-2'
                    }, [
                        React.createElement('p', {
                            className: 'text-gray-400'
                        }, 'Equity'),
                        React.createElement('p', {
                            className: 'text-2xl font-bold'
                        }, `$${parseFloat(account.equity).toLocaleString()}`)
                    ]),
                    React.createElement('div', {
                        className: 'space-y-2'
                    }, [
                        React.createElement('p', {
                            className: 'text-gray-400'
                        }, 'Buying Power'),
                        React.createElement('p', {
                            className: 'text-2xl font-bold'
                        }, `$${parseFloat(account.buying_power).toLocaleString()}`)
                    ]),
                    React.createElement('div', {
                        className: 'space-y-2'
                    }, [
                        React.createElement('p', {
                            className: 'text-gray-400'
                        }, 'Cash'),
                        React.createElement('p', {
                            className: 'text-2xl font-bold'
                        }, `$${parseFloat(account.cash).toLocaleString()}`)
                    ])
                ])
            ]),

            // Performance Metrics Card
            React.createElement('div', {
                key: 'performance-metrics',
                className: 'bg-gray-800 rounded-lg p-6 space-y-4'
            }, [
                React.createElement('h2', {
                    className: 'text-xl font-bold'
                }, 'Performance Metrics'),
                React.createElement('div', {
                    className: 'grid grid-cols-4 gap-6'
                }, [
                    React.createElement('div', {
                        className: 'space-y-2'
                    }, [
                        React.createElement('p', {
                            className: 'text-gray-400'
                        }, 'Week over Week'),
                        React.createElement('p', {
                            className: `text-2xl font-bold ${performanceMetrics.wow.percentage >= 0 ? 'text-green-500' : 'text-red-500'}`
                        }, `${performanceMetrics.wow.percentage.toFixed(2)}%`),
                        React.createElement('p', {
                            className: 'text-gray-400'
                        }, `$${performanceMetrics.wow.dollars.toFixed(2)}`)
                    ]),
                    React.createElement('div', {
                        className: 'space-y-2'
                    }, [
                        React.createElement('p', {
                            className: 'text-gray-400'
                        }, 'Month over Month'),
                        React.createElement('p', {
                            className: `text-2xl font-bold ${performanceMetrics.mom.percentage >= 0 ? 'text-green-500' : 'text-red-500'}`
                        }, `${performanceMetrics.mom.percentage.toFixed(2)}%`),
                        React.createElement('p', {
                            className: 'text-gray-400'
                        }, `$${performanceMetrics.mom.dollars.toFixed(2)}`)
                    ]),
                    React.createElement('div', {
                        className: 'space-y-2'
                    }, [
                        React.createElement('p', {
                            className: 'text-gray-400'
                        }, 'Trades Won'),
                        React.createElement('p', {
                            className: 'text-2xl font-bold text-green-500'
                        }, performanceMetrics.trades.won)
                    ]),
                    React.createElement('div', {
                        className: 'space-y-2'
                    }, [
                        React.createElement('p', {
                            className: 'text-gray-400'
                        }, 'Trades Lost'),
                        React.createElement('p', {
                            className: 'text-2xl font-bold text-red-500'
                        }, performanceMetrics.trades.lost)
                    ])
                ])
            ]),

            // Positions Table (only shown when positions exist)
            positions.length > 0 && React.createElement('div', {
                key: 'positions-table',
                className: 'bg-gray-800 rounded-lg p-6 space-y-4'
            }, [
                React.createElement('h2', {
                    className: 'text-xl font-bold'
                }, 'Open Positions'),
                React.createElement('div', {
                    className: 'overflow-x-auto'
                }, React.createElement('table', {
                    className: 'w-full'
                }, [
                    React.createElement('thead', null,
                        React.createElement('tr', null, [
                            React.createElement('th', { className: 'text-left p-2' }, 'Symbol'),
                            React.createElement('th', { className: 'text-right p-2' }, 'Quantity'),
                            React.createElement('th', { className: 'text-right p-2' }, 'Entry Price'),
                            React.createElement('th', { className: 'text-right p-2' }, 'Current Price'),
                            React.createElement('th', { className: 'text-right p-2' }, 'P/L'),
                            React.createElement('th', { className: 'text-right p-2' }, 'Actions')
                        ])
                    ),
                    React.createElement('tbody', null,
                        positions.map(position => 
                            React.createElement('tr', {
                                key: position.symbol,
                                className: 'border-t border-gray-700'
                            }, [
                                React.createElement('td', { className: 'p-2' }, position.symbol),
                                React.createElement('td', { className: 'text-right p-2' }, position.qty),
                                React.createElement('td', { className: 'text-right p-2' }, `$${parseFloat(position.entry_price).toFixed(2)}`),
                                React.createElement('td', { className: 'text-right p-2' }, `$${parseFloat(position.current_price).toFixed(2)}`),
                                React.createElement('td', { 
                                    className: `text-right p-2 ${parseFloat(position.unrealized_plpc) >= 0 ? 'text-green-500' : 'text-red-500'}`
                                }, `${(parseFloat(position.unrealized_plpc) * 100).toFixed(2)}%`),
                                React.createElement('td', { className: 'text-right p-2' },
                                    React.createElement('button', {
                                        className: 'bg-red-500 text-white px-2 py-1 rounded text-sm',
                                        onClick: () => handleClosePosition(position.symbol)
                                    }, 'Close')
                                )
                            ])
                        )
                    )
                ]))
            ]),

            // Recent Trades Table (only shown when trades exist)
            trades.length > 0 && React.createElement('div', {
                key: 'trades-table',
                className: 'bg-gray-800 rounded-lg p-6 space-y-4'
            }, [
                React.createElement('h2', {
                    className: 'text-xl font-bold'
                }, 'Recent Trades'),
                React.createElement('div', {
                    className: 'overflow-x-auto'
                }, React.createElement('table', {
                    className: 'w-full'
                }, [
                    React.createElement('thead', null,
                        React.createElement('tr', null, [
                            React.createElement('th', { className: 'text-left p-2' }, 'Time'),
                            React.createElement('th', { className: 'text-left p-2' }, 'Symbol'),
                            React.createElement('th', { className: 'text-left p-2' }, 'Side'),
                            React.createElement('th', { className: 'text-right p-2' }, 'Quantity'),
                            React.createElement('th', { className: 'text-right p-2' }, 'Price')
                        ])
                    ),
                    React.createElement('tbody', null,
                        trades.map((trade, index) =>
                            React.createElement('tr', {
                                key: index,
                                className: 'border-t border-white/10 hover:bg-white/5'
                            }, [
                                React.createElement('td', {
                                    className: 'p-4'
                                }, new Date(trade.timestamp).toLocaleTimeString()),
                                React.createElement('td', {
                                    className: 'p-4 font-mono'
                                }, trade.symbol),
                                React.createElement('td', {
                                    className: 'p-4'
                                }, React.createElement('span', {
                                    className: `rounded px-2 py-1 text-xs ${trade.side.toLowerCase() === 'buy' ? 'bg-green-500/10 text-green-500' : 'bg-red-500/10 text-red-500'}`
                                }, trade.side.toUpperCase())),
                                React.createElement('td', {
                                    className: 'p-4 text-right'
                                }, trade.quantity),
                                React.createElement('td', {
                                    className: 'p-4 text-right'
                                }, `$${parseFloat(trade.price).toFixed(2)}`)
                            ])
                        )
                    )
                ]))
            ])
        ])
    );
};