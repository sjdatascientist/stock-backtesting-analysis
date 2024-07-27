import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import plotly.graph_objects as go
from nsepython import equity_history
from datetime import date, timedelta
from backtesting import Backtest, Strategy
from backtesting.lib import crossover
from backtesting.test import SMA

# Set the page configuration to wide mode
st.set_page_config(layout="wide")

top20_nifty_stocks = pd.read_csv('T20-GL-gainers-NIFTY-26-Jul-2024.csv')

# Define the start and end dates for the 5 year period
end_date = date.today()
start_date = end_date - timedelta(days=5*365)
end_date_str = end_date.strftime('%d-%m-%Y')
start_date_str = start_date.strftime('%d-%m-%Y')

# Define functions
def get_stock_data(stock_name: str, start_date=start_date_str, end_date=end_date_str) -> pd.DataFrame:
    stock_data_raw = equity_history(stock_name, 'EQ', start_date, end_date)
    important_cols = ['CH_SYMBOL', 'CH_TIMESTAMP', 'CH_TRADE_HIGH_PRICE', 'CH_TRADE_LOW_PRICE',
                      'CH_OPENING_PRICE', 'CH_CLOSING_PRICE', 'CH_TOT_TRADED_QTY']
    stock_data = stock_data_raw[important_cols]
    stock_data = stock_data.rename(columns={
        'CH_SYMBOL': 'Symbol',
        'CH_TIMESTAMP': 'Date',
        'CH_TRADE_HIGH_PRICE': 'High',
        'CH_TRADE_LOW_PRICE': 'Low',
        'CH_OPENING_PRICE': 'Open',
        'CH_CLOSING_PRICE': 'Close',
        'CH_TOT_TRADED_QTY': 'Volume'
    })
    stock_data['Date'] = pd.to_datetime(stock_data['Date'])
    stock_data['Year'] = stock_data['Date'].dt.year
    stock_data = stock_data[['Symbol', 'Date', 'Year', 'Low', 'High', 'Open', 'Close', 'Volume']].sort_values(by='Date')
    return stock_data

def simple_moving_average_crossover(df):
    df['50d'] = df['Close'].rolling(window=50).mean()
    df['200d'] = df['Close'].rolling(window=200).mean()
    df['Signal'] = (df['50d'] > df['200d']).astype(int)
    df['Entry/Exit'] = df['Signal'].diff()
    df['Strategy Returns'] = df['Close'].pct_change() * df['Signal'].shift(1)
    df['Cumulative Strategy Returns'] = (1 + df['Strategy Returns']).cumprod() - 1
    return df

def plot_backtested_data(backtested_data: pd.DataFrame, stock_name: str):
    df = backtested_data

    # Create the tooltip text with labels for candlestick
    df['tooltip'] = (
            'Date: ' + df['Date'].dt.strftime('%Y-%m-%d') + '<br>' +
            'Open: ' + df['Open'].astype(str) + '<br>' +
            'Low: ' + df['Low'].astype(str) + '<br>' +
            'Close: ' + df['Close'].astype(str) + '<br>' +
            'High: ' + df['High'].astype(str) + '<br>' +
            'Volume: ' + df['Volume'].astype(str)
    )

    # Create the candlestick trace
    candlestick = go.Candlestick(
        x=df['Date'],  # Change x-axis to df['Date']
        open=df['Open'],
        high=df['High'],
        low=df['Low'],
        close=df['Close'],
        name='Candlestick',
        hovertext=df['tooltip'],  # Use the custom tooltip
        hoverinfo='text'  # Show custom tooltip
    )

    # Create the 50-day SMA trace
    sma50 = go.Scatter(
        x=df['Date'],  # Change x-axis to df['Date']
        y=df['50d'],
        mode='lines',
        name='50-day SMA',
        line=dict(color='darkorchid')
    )

    # Create the 200-day SMA trace
    sma200 = go.Scatter(
        x=df['Date'],  # Change x-axis to df['Date']
        y=df['200d'],
        mode='lines',
        name='200-day SMA',
        line=dict(color='violet')
    )

    # Create the buy signal trace with tooltip
    buy_signals = df[df['Entry/Exit'] == 1]
    buy_trace = go.Scatter(
        x=buy_signals['Date'],  # Change x-axis to df['Date']
        y=buy_signals['Close'],
        mode='markers',
        marker=dict(
            symbol='triangle-up',
            size=25,
            color='green'
        ),
        name='Buy Signal',
        hovertext=(
                'Date: ' + buy_signals['Date'].dt.strftime('%Y-%m-%d') + '<br>' +
                'Close: ' + buy_signals['Close'].astype(str) + '<br>' +
                'Signal: Buy'
        ),
        hoverinfo='text'  # Show custom tooltip
    )

    # Create the sell signal trace with tooltip
    sell_signals = df[df['Entry/Exit'] == -1]
    sell_trace = go.Scatter(
        x=sell_signals['Date'],  # Change x-axis to df['Date']
        y=sell_signals['Close'],
        mode='markers',
        marker=dict(
            symbol='triangle-down',
            size=25,
            color='red'
        ),
        name='Sell Signal',
        hovertext=(
                'Date: ' + sell_signals['Date'].dt.strftime('%Y-%m-%d') + '<br>' +
                'Close: ' + sell_signals['Close'].astype(str) + '<br>' +
                'Signal: Sell'
        ),
        hoverinfo='text'  # Show custom tooltip
    )

    # Create the layout with quarterly ticks
    layout = go.Layout(
        title=f"{stock_name} - Simple Moving Average Crossover Strategy",
        xaxis_title="Date",
        yaxis_title="Price",
        xaxis_rangeslider_visible=False,
        width=1700,
        height=900,
        xaxis=dict(
            constrain='domain',
            range=[df['Date'].min() - pd.Timedelta(days=15), df['Date'].max() + pd.Timedelta(days=15)],  # Add padding
            tickvals=pd.date_range(start=df['Date'].min(), end=df['Date'].max(), freq='Q'),  # Quarterly ticks
            ticktext=pd.date_range(start=df['Date'].min(), end=df['Date'].max(), freq='Q').strftime('%Y-%m')  # Format ticks as Year-Month
        )
    )

    # Create the figure and plot
    fig = go.Figure(data=[candlestick, sma50, sma200, buy_trace, sell_trace], layout=layout)
    fig.update_layout(template='plotly_white')
    return fig


class SMACross(Strategy):
    def init(self):
        self.sma50 = self.I(SMA, self.data.Close, 50)
        self.sma200 = self.I(SMA, self.data.Close, 200)

    def next(self):
        if crossover(self.sma50, self.sma200):
            self.buy()
        elif crossover(self.sma200, self.sma50):
            self.sell()

def backtesting_with_lib(data: pd.DataFrame):
    if data.empty:
        return None, None
    backtest = Backtest(data, SMACross, commission=.002, exclusive_orders=True)
    stats = backtest.run()
    return stats

# STREAMLIT APP

st.title("Stock Price Analysis App")
st.write('The app implements a simple moving average crossover strategy with 50-day moving average and 200-day moving'
         'average in Python and then backtests it, showing you the stock data, key metrics, and visualization.')
st.write('NOTE: The default time frame is 5 Years')
st.subheader('Top 20 Gainers Stocks by NSE India')
st.dataframe(top20_nifty_stocks)

# Sidebar Content
st.sidebar.header("User Inputs")
st.sidebar.write('Choose from these 20 stocks below:')
st.sidebar.markdown("[NSE Top 20 Stocks](https://www.nseindia.com/market-data/top-gainers-losers)")

# User Inputs
stock_name = st.sidebar.text_input("Enter Stock Symbol (e.g., CIPLA, RELIANCE)")
start_date = st.sidebar.date_input("Start Date", pd.to_datetime("2019-07-29"))
end_date = st.sidebar.date_input("End Date", pd.to_datetime("today"))

# Main Content
if st.sidebar.button("Get Stock Data"):
    with st.spinner("Fetching stock data..."):
        stock_data = get_stock_data(stock_name, start_date.strftime('%d-%m-%Y'), end_date.strftime('%d-%m-%Y'))
        if stock_data.empty:
            st.error("No data found for the specified stock and date range.")
        else:
            st.success(f"Data fetched for {stock_name} from {start_date} to {end_date}.")
            st.subheader(f"Stock Data for Stock Name: {stock_name}")
            st.dataframe(stock_data)

            st.subheader("Key Metrics")
            stats = backtesting_with_lib(stock_data)
            st.dataframe(pd.DataFrame(stats, columns=['Metrics-Values']))

            st.subheader("Backtesting Analysis")
            # Calculate moving averages and backtest
            stock_data = simple_moving_average_crossover(stock_data)
            fig = plot_backtested_data(stock_data, stock_name)
            st.plotly_chart(fig)


            # Calculate moving averages and backtest
            # stock_data = simple_moving_average_crossover(stock_data)

            # # Plot the data
            # fig = plot_backtested_data(stock_data)
            # st.plotly_chart(fig)

            st.subheader("Cumulative Strategy Returns")
            st.line_chart(stock_data['Cumulative Strategy Returns'])

            # Plotting Backtesting Viz with `backtesting` library
            st.subheader('Plotting with Backtesting Library')
            st.write('Note: A new tab will open for the visualization.')
            bt = Backtest(stock_data, SMACross, commission=.002, exclusive_orders=True)
            bt.run()
            bt.plot()

# Footer
st.sidebar.text("Developed by Shubham Jangra")
st.sidebar.markdown("[Github Profile Link](https://github.com/sjdatascientist)")