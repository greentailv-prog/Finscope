# -*- coding: utf-8 -*-
"""
Created on Mon Dec  3 14:05:13 2019
@author: lingqiang
"""
from iFinDPy import * 
import pandas as pd
import pandas as pd
pd.set_option('display.max_columns', 100000, 'display.max_rows', 100000)#设置显示行数
thsLogin = THS_iFinDLogin('账号','密码')#调用登录函数，账号密码登录）
if not (thsLogin == 0 or thsLogin == -201):
    print("登录失败")
else:
#1、高频序列接口使用案例 
    print("高频序列 输出结果========================分隔线===========================")
    data=THS_HighFrequenceSequence('300033.SZ','open;high;low;close','CPS:no,baseDate:1900-01-01,MaxPoints:50000,Fill:Previous,Interval:1','2019-07-31 09:15:00','2019-07-31 15:15:00')
    data1=THS_Trans2DataFrame(data)
    print(data1); 

#2、实时行情接口使用案例
    print("实时行情 输出结果========================分隔线===========================")
    data=THS_RealtimeQuotes('300033.SZ','open;high;low;latest;changeRatio;amount;volume;bid1;ask1')
    data1=THS_Trans2DataFrame(data)
    print(data1); 

#3、实时行情接口使用案例
    print("历史行情 输出结果========================分隔线===========================")
    data=THS_HistoryQuotes('300033.SZ,600000.SH','preClose,open,high,low,close,avgPrice,change,changeRatio,volume,turnoverRatio,amount,transactionAmount','Interval:D,CPS:1,baseDate:1900-01-01,Currency:YSHB,fill:Previous','2018-07-31','2019-07-31')
    data1=THS_Trans2DataFrame(data)
    print(data1);
    
#4、基础数据接口使用案例
    print("基础数据 输出结果========================分隔线===========================")
    data=THS_BasicData('300033.SZ','ths_stock_short_name_stock;ths_stock_code_stock;ths_pe_stock;ths_pb_stock',';;2019-07-31,101;2019-07-31,100')
    data1=THS_Trans2DataFrame(data)
    print(data1); 

#5、日期序列接口使用案例
    print("日期序列 输出结果========================分隔线===========================")
    data=THS_DateSerial('300033.SZ','ths_af_stock;ths_close_price_stock;ths_low_stock;ths_high_price_stock;ths_open_price_stock',';100;100;100;100','Days:Alldays,Fill:Previous,Interval:D','2019-01-28','2019-07-31')
    data1=THS_Trans2DataFrame(data)
    print(data1); 
    
#6、数据池接口使用案例
    print("数据池 输出结果========================分隔线===========================")
    data=THS_DataPool('block','2019-07-31;001005010','date:Y,thscode:Y,security_name:Y')
    data1=THS_Trans2DataFrame(data)
    print(data1); 

#7、EDB经济数据库接口使用案例
    print("EDB经济数据库 输出结果========================分隔线===========================")
    data=THS_EDBQuery('M001620326;M002822183;M002834227;M002822182','2018-07-31','2019-07-31')
    data1=THS_Trans2DataFrame(data)
    print(data1);

#8、i问财接口使用案例
    print("i问财 输出结果========================分隔线===========================")
    data=THS_iwencai('今日涨停股票','stock')
    print(data);

#9、组合查询应用案例（获取某个同花顺行业指数下的成分股实时行情数据）
    print("组合查询应用案例  输出结果========================分隔线===========================")
    
    from iFinDPy import *
    import time
    import numpy as np
    import datetime
    pd.set_option('display.max_columns', 100000, 'display.max_rows', 100000)#设置显示行数
    time=time.strftime('%Y-%m-%d',time.localtime(time.time())) #获取最新日期的数据
    thsData=THS_DataPool('index',time+";884183.TI",'date:Y,thscode:Y,security_name:Y') #获取所传参数的当天日期的同花顺行业指数（船舶制造）成分股
    ths_codes=','.join(thsData['tables'][0]['table']['THSCODE']) 
    thsdata=THS_RealtimeQuotes(ths_codes,'open;high;low;latest;changeRatio;amount;volume;bid1;ask1;bidSize1;askSize1;inflow;outflow')#获取所传参数的股票代码的当日实时的基本行情、盘口行情、资金流向数据
    result=THS_Trans2DataFrame(thsdata)
    print(result)