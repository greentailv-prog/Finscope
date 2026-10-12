# -*- coding: utf-8 -*-
"""
版本：1.0.0.1
作者：邓猛 dengmeng@myhexin.com 时间：20141106
更新时间：20141106 增加数据接口
文档介绍：iFinD Python接口程序。需与FTDataInterface.dll一起使用
修改历史：
版权：同花顺iFinD

"""

from ctypes import *
import sys
import re
import string
import types
import platform
import os
import threading
import copy
import json
from datetime import datetime,date,time,timedelta
from collections import OrderedDict
if platform.python_version().find('3.') < 0:
        stdi,stdo,stde=sys.stdin,sys.stdout,sys.stderr 
        reload(sys) 
        sys.stdin,sys.stdout,sys.stderr=stdi,stdo,stde
        sys.setdefaultencoding('utf-8');

class THSData:
    def __init__(self):
        self.errorcode = 0
        self.errmsg = '';
        self.indicators = list()
        self.datatype = list()
        self.perf = 0
        self.dataVol = 0
        self.time = list()
        self.thscode = list()
        self.data = None
        
    def __str__(self):
        return "errorcode=%s\nerrmsg=%s\ndata=%s" % (self.errorcode,self.errmsg,str(self.data))
        
    def __repr__(self):
        try:
            return "errorcode=%s\nerrmsg=%s\ndata=%s" % (self.errorcode,self.errmsg,str(self.data))
        except:
            return "errorcode={}\nerrmsg={}\ndata={}".format(self.errorcode,self.errmsg,self.data)
        
    def formatResult(self,result,format):
        if(len(result) <= 0):
            self.errorcode = -6000
            self.errmsg = 'The result is empty'
            return;
        obj = dict()
        try:
            obj = json.loads(result.decode(iFinD.decodeMethod,'ignore'))
        except:
            ret = result.decode(iFinD.decodeMethod,'ignore')
            obj = loads_str(ret)
        self.errorcode = obj.get('errorcode',0)
        self.errmsg = obj.get('errmsg','')
        if(self.errorcode != 0):
            return;
        dt = obj.get('datatype',[])
        self.datatype = [ x.get('type') for x in dt]
        self.perf = obj.get('perf',0)
        self.dataVol = obj.get('dataVol',0)
        
        if(('tables') in obj):
            tables = obj['tables']
            codelen = len(tables)
            for i in range(codelen):
                if ('time') in tables[i]:
                    self.time= tables[i]['time'];
                    break;
            
            self.thscode = [ x.get('thscode') for x in tables]
            if format == 'format:json':
                self.data = result
            elif format == 'format:list':
                self.data = obj['tables']
            elif format == 'format:dataframe':
                import numpy as np,pandas as pd
                dataframe = pd.DataFrame()
                if (self.errorcode != 0):
                    self.data = dataframe
                else:
                    try:
                        self.data = THS_Trans2DataFrame(result)
                    except:
                        self.errorcode = -6001   #转换dataframe失败错误码
                        self.errmsg = 'Failed to convert dataframe'
                        self.data = dataframe
    
    def formatResultDate(self,result,format):   #新版日期查询函数与日期偏移函数
        if(len(result) <= 0):
            self.errorcode = -6000
            self.errmsg = 'The result is empty'
            return;
        obj = dict()
        try:
            obj = json.loads(result.decode(iFinD.decodeMethod))
        except:
            ret = result.decode(iFinD.decodeMethod)
            obj = loads_str(ret)
        self.errorcode = obj.get('errorcode',0)
        self.errmsg = obj.get('errmsg','')
        if(self.errorcode != 0):
            return;
        dt = obj.get('datatype',[])
        self.datatype = [ x.get('type') for x in dt]
        self.perf = obj.get('perf',0)
        self.dataVol = obj.get('dataVol',0)
        
        if(('tables') in obj):
            tables = obj['tables']
            if(isinstance(tables,dict) and (('time') in tables)):
                self.time=tables.get('time',[])
            
            if format == 'format:json':
                self.data = result
            elif format == 'format:dict':
                oddict = json.loads(result.decode(iFinD.decodeMethod),object_pairs_hook=OrderedDict)
                self.data = oddict['tables']
            elif format == 'format:str':
                if(isinstance(tables,dict) and (('time') in tables)):
                    self.data = ",".join(self.time)
                elif(('count') in tables):
                    self.data = tables['count']
                    
                    
def THS_iFinDLogin(username, password): 
    return iFinD.FT_iFinDLogin(username, password);

def THS_iFinDLogout():
    return iFinD.FT_iFinDLogout();
    
def THS_SetLanguage(language):
    return iFinD.FT_SetLanguage(language);

def THS_HighFrequenceSequence(thscode, jsonIndicator, jsonparam, begintime, endtime, outflag=False):
    thscodestr = thscode
    if(isinstance(thscode,list)):
        thscodestr = ",".join(thscode)
    return iFinD.FTQuerySynTHS_HighFrequenceSequence(thscodestr, jsonIndicator, jsonparam, begintime, endtime, outflag);
    
def THS_HF(thscode, jsonIndicator, jsonparam, begintime, endtime, format='format:dataframe'):
    thscodestr = thscode
    if(isinstance(thscode,list)):
        thscodestr = ",".join(thscode)
    return iFinD.FTQuerySynTHS_HF(thscodestr, jsonIndicator, jsonparam, begintime, endtime, format);

def THS_RealtimeQuotes(thscode, jsonIndicator, jsonparam="", outflag=False):
    thscodestr = thscode
    if(isinstance(thscode,list)):
        thscodestr = ",".join(thscode)
    if(jsonparam == ""):
        jsonparam="pricetype:1";
    return iFinD.FTQuerySynTHS_RealtimeQuotes(thscodestr,jsonIndicator,jsonparam,outflag);
    
def THS_RQ(thscode, jsonIndicator, jsonparam="", format='format:dataframe'):
    thscodestr = thscode
    if(isinstance(thscode,list)):
        thscodestr = ",".join(thscode)
    if(jsonparam == ""):
        jsonparam="pricetype:1";
    return iFinD.FTQuerySynTHS_RQ(thscodestr,jsonIndicator,jsonparam,format);

def THS_HistoryQuotes(thscode, jsonIndicator, jsonparam, begintime, endtime, outflag=False):
    thscodestr = thscode
    if(isinstance(thscode,list)):
        thscodestr = ",".join(thscode)
    return iFinD.FTQuerySynTHS_HisQuote(thscodestr,jsonIndicator,jsonparam,begintime,endtime,outflag);
    
def THS_HQ(thscode, jsonIndicator, jsonparam, begintime, endtime, format='format:dataframe'):
    thscodestr = thscode
    if(isinstance(thscode,list)):
        thscodestr = ",".join(thscode)
    return iFinD.FTQuerySynTHS_HQ(thscodestr,jsonIndicator,jsonparam,begintime,endtime,format);

def THS_HD(thscode, jsonIndicator, jsonparam, begintime, endtime, format='format:dataframe'):
    thscodestr = thscode
    if(isinstance(thscode,list)):
        thscodestr = ",".join(thscode)
    return iFinD.FTQuerySynTHS_HD(thscodestr,jsonIndicator,jsonparam,begintime,endtime,format);

def THS_BasicData(thsCode, indicatorName, paramOption, outflag=False):
    thscodestr = thsCode
    if(isinstance(thsCode,list)):
        thscodestr = ",".join(thsCode)
    return iFinD.FTQuerySynTHS_BasicData(thscodestr,indicatorName,paramOption,outflag);
    
def THS_BD(thsCode, indicatorName, paramOption, format='format:dataframe'):
    thscodestr = thsCode
    if(isinstance(thsCode,list)):
        thscodestr = ",".join(thsCode)
    return iFinD.FTQuerySynTHS_BD(thscodestr,indicatorName,paramOption,format);

def THS_Snapshot(thscode, jsonIndicator, jsonparam, begintime, endtime, outflag=False):
    thscodestr = thscode
    if(isinstance(thscode,list)):
        thscodestr = ",".join(thscode)
    return iFinD.FTQuerySynTHS_Snapshot(thscodestr,jsonIndicator,jsonparam,begintime,endtime,outflag);
    
def THS_SS(thscode, jsonIndicator, jsonparam, begintime, endtime, format='format:dataframe'):
    thscodestr = thscode
    if(isinstance(thscode,list)):
        thscodestr = ",".join(thscode)
    return iFinD.FTQuerySynTHS_SS(thscodestr,jsonIndicator,jsonparam,begintime,endtime,format);

def THS_DateSequence(thscode,jsonIndicator,jsonparam,begintime,endtime,outflag=False):
    thscodestr = thscode
    if(isinstance(thscode,list)):
        thscodestr = ",".join(thscode)
    return iFinD.FTQuerySynTHS_DateSequence(thscodestr,jsonIndicator,jsonparam,begintime,endtime,outflag);

def THS_DataPool(DataPoolname,paramname,FunOption,outflag=False):
    return iFinD.FTQuerySynTHS_DataPool(DataPoolname,paramname,FunOption,outflag)
    
def THS_DP(DataPoolname,paramname,FunOption,format='format:dataframe'):
    return iFinD.FTQuerySynTHS_DP(DataPoolname,paramname,FunOption,format)

def THS_DR(TPname,paramname,FunOption,format='format:dataframe'):
    return iFinD.FTQuerySynTHS_DR(TPname,paramname,FunOption,format)
    
def THS_RPT(TPname,version,paramname,FunOption,format='format:dataframe'):
    return iFinD.FTQuerySynTHS_RPT(TPname,version,paramname,FunOption,format)
    
def THS_FEB(params,FunOption,format='format:dataframe'):
    return iFinD.FTQuerySynTHS_FEB(params,FunOption,format)

def THS_iResearch(name,paramname,FunOption,format='format:dataframe'):
    return iFinD.FTQuerySynTHS_iResearch(name,paramname,FunOption,format)

def THS_iEvent(name,paramname,FunOption,format='format:dataframe'):
    return iFinD.FTQuerySynTHS_iEvent(name,paramname,FunOption,format)

def THS_iTranslate(name,paramname,FunOption):
    return iFinD.FTQuerySynTHS_iTranslate(name,paramname,FunOption)    
    
def THS_EDBQuery(indicators, begintime, endtime,outflag=False):
    return iFinD.FT_EDBQuery(indicators,begintime,endtime,outflag)
    
def THS_EDB(indicators, param, begintime, endtime,format='format:dataframe'):
    return iFinD.FT_EDB(indicators,param,begintime,endtime,format)

def THS_iwencai(query,domain,outflag=False):
    return iFinD.FT_iwencai(query,domain,outflag)
    
def THS_WCQuery(query,domain,format='format:dataframe'):
    return iFinD.FT_WCQuery(query,domain,format)
    
def THS_WC(query,domain,format='format:dataframe'):
    return iFinD.FT_WC(query,domain,format)
    
def THS_DataStatistics(outflag=False):
    return iFinD.FT_DataStastics(outflag)

def THS_GetErrorInfo(errorcode,outflag=False):
    return iFinD.FT_GetErrorInfo(errorcode,outflag);
def THS_DateQuery(exchange, params, begintime, endtime, outflag=False):
    return iFinD.FT_DateQuery(exchange, params, begintime, endtime, outflag)
def THS_Date_Query(exchange, params, begintime, endtime, format='format:str', **extra_params):
    params = handle_params('utf8', params, **extra_params)
    return iFinD.FT_Date_Query(exchange, params, begintime, endtime, format)
def THS_DateOffset(exchange, params, endtime, outflag=False):
    return iFinD.FT_DateOffset(exchange, params, endtime, outflag)
def THS_Date_Offset(exchange, params, endtime, format='format:str', **extra_params):
    params = handle_params('gbk', params, **extra_params)
    return iFinD.FT_Date_Offset(exchange, params, endtime, format)
def THS_DateCount(exchange, params, begintime, endtime, outflag=False):
    return iFinD.FT_DateCount(exchange, params, begintime, endtime, outflag)
def THS_DateSerial(thscode, jsonIndicator, jsonparam, globalparam, begintime, endtime, outflag=False):
    thscodestr = thscode
    if(isinstance(thscode,list)):
        thscodestr = ",".join(thscode)
    return iFinD.FTQueryTHS_DateSerial(thscodestr, jsonIndicator, jsonparam, globalparam, begintime, endtime, outflag);

def THS_DS(thscode, jsonIndicator, jsonparam, globalparam, begintime, endtime, format='format:dataframe'):
    thscodestr = thscode
    if(isinstance(thscode,list)):
        thscodestr = ",".join(thscode)
    return iFinD.FTQueryTHS_DS(thscodestr, jsonIndicator, jsonparam, globalparam, begintime, endtime, format);

def THS_Special_ShapePredict(thscode, param, begintime, endtime, outflag=False):
    return iFinD.FTQuerySynTHS_Special_ShapePredict(thscode, param, begintime, endtime, outflag);
def THS_Special_StockLink(thscode, param, outflag=False):
    return iFinD.FTQuerySynTHS_Special_StockLink(thscode, param, outflag);
def THS_Special(type, thscode, param, outflag=False):
    return iFinD.FTQuerySynTHS_Special(type, thscode, param, outflag);
    
def THS_toTHSCODE(transcontents, param, format='format:dataframe'):
    return iFinD.FTQuerySynTHS_toTHSCODE(transcontents, param, format);
    
def THS_realTimeValuation(thscode, param, output, format='format:dataframe'):
    thscodestr = thscode
    if(isinstance(thscode,list)):
        thscodestr = ",".join(thscode)
    return iFinD.FTQuerySynTHS_realTimeValuation(thscodestr, param, output, format);
    
def THS_finalValuation(thscode, param, output, format='format:dataframe'):
    thscodestr = thscode
    if(isinstance(thscode,list)):
        thscodestr = ",".join(thscode)
    return iFinD.FTQuerySynTHS_finalValuation(thscodestr, param, output, format);
    
def THS_ReportQuery(thscode, param, output, format='format:dataframe'):
    thscodestr = thscode
    if(isinstance(thscode,list)):
        thscodestr = ",".join(thscode)
    return iFinD.FTQuerySynTHS_ReportQuery(thscodestr, param, output, format);

def THS_AsyHighFrequenceSequence(thscode, jsonIndicator, jsonparam, begintime, endtime,Callback,pUser,iD):
    thscodestr = thscode
    if(isinstance(thscode,list)):
        thscodestr = ",".join(thscode)
    return iFinD.FTQueryTHS_HighFrequenceSequence(thscodestr, jsonIndicator, jsonparam, begintime, endtime,Callback,pUser,iD)
    
def THS_AsyRealtimeQuotes(thscode, jsonIndicator, jsonparam,Callback,pUser,ID):
    thscodestr = thscode
    if(isinstance(thscode,list)):
        thscodestr = ",".join(thscode)
    return iFinD.FTQueryTHS_RealtimeQuotes(thscodestr,jsonIndicator,jsonparam,Callback,pUser,ID);

def THS_AsyHistoryQuotes(thscode, jsonIndicator, jsonparam, begintime, endtime,Callback,pUser,iD):
    thscodestr = thscode
    if(isinstance(thscode,list)):
        thscodestr = ",".join(thscode)
    return iFinD.FTQueryTHS_HisQuote(thscodestr,jsonIndicator,jsonparam,begintime,endtime,Callback,pUser,iD);

def THS_AsyBasicData(thsCode, indicatorName, paramOption,Callback,pUser,iD):
    thscodestr = thsCode
    if(isinstance(thsCode,list)):
        thscodestr = ",".join(thsCode)
    return iFinD.FTQueryTHS_BasicData(thscodestr,indicatorName,paramOption,Callback,pUser,iD);

def THS_AsyDateSequence(thscode,jsonIndicator,jsonparam,begintime,endtime,Callback,pUser,iD):
    thscodestr = thscode
    if(isinstance(thscode,list)):
        thscodestr = ",".join(thscode)
    return iFinD.FTQueryTHS_DateSequence(thscodestr,jsonIndicator,jsonparam,begintime,endtime,Callback,pUser,iD);

def THS_AsyEDBQuery(indicators, begintime, endtime,Callback,pUser,iD):
    return iFinD.FTQueryTHS_EDBQuery(indicators,begintime,endtime,Callback,pUser,iD)
    
def THS_AsyEDB(indicators, param, begintime, endtime,Callback,pUser,iD):
    return iFinD.FTQueryTHS_EDB(indicators,param,begintime,endtime,Callback,pUser,iD)

def THS_Asyiwencai(query,domain,Callback,pUser,iD):
    return iFinD.FTQueryTHS_iwencai(query,domain,Callback,pUser,iD)
    
def THS_AsyWCQuery(query,domain,Callback,pUser,iD):
    return iFinD.FTQueryTHS_WCQuery(query,domain,Callback,pUser,iD)
    
def THS_AsyDataPool(DataPoolname,paramname,FunOption,Callback,pUser,iD):
    return iFinD.FTQueryTHS_DataPool(DataPoolname,paramname,FunOption,Callback,pUser,iD)
    
def THS_AsyDR(TPname,paramname,FunOption,Callback,pUser,iD):
    return iFinD.FTQueryTHS_DR(TPname,paramname,FunOption,Callback,pUser,iD)
    
def THS_AsyRPT(TPname,version,paramname,FunOption,Callback,pUser,iD):
    return iFinD.FTQueryTHS_RPT(TPname,version,paramname,FunOption,Callback,pUser,iD)
    
def THS_AsyFEB(params,FunOption,Callback,pUser,iD):
    return iFinD.FTQueryTHS_FEB(params,FunOption,Callback,pUser,iD)
    
def THS_AsyiResearch(name,paramname,FunOption,Callback,pUser,iD):
    return iFinD.FTQueryTHS_iResearch(name,paramname,FunOption,Callback,pUser,iD)
    
def THS_AsyiEvent(name,paramname,FunOption,Callback,pUser,iD):
    return iFinD.FTQueryTHS_iEvent(name,paramname,FunOption,Callback,pUser,iD)
    
def THS_AsyiTranslate(name,paramname,FunOption,Callback,pUser,iD):
    return iFinD.FTQueryTHS_iTranslate(name,paramname,FunOption,Callback,pUser,iD)

def THS_AsySnapshot(thscode, jsonIndicator, jsonparam, begintime, endtime,Callback,pUser,iD):
    thscodestr = thscode
    if(isinstance(thscode,list)):
        thscodestr = ",".join(thscode)
    return iFinD.FTQueryTHS_Snapshot(thscodestr,jsonIndicator,jsonparam,begintime,endtime,Callback,pUser,iD);

def THS_AsyDateSerial(thscode,jsonIndicator,jsonparam,globalparam,begintime,endtime,Callback,pUser,iD):
    thscodestr = thscode
    if(isinstance(thscode,list)):
        thscodestr = ",".join(thscode)
    return iFinD.FTQueryTHS_AsyDateSerial(thscodestr,jsonIndicator,jsonparam,globalparam,begintime,endtime,Callback,pUser,iD);

def THS_AsySpecial_ShapePredict(thscode,param,begintime,endtime,Callback,pUser,iD):
    return iFinD.FTQueryTHS_AsySpecial_ShapePredict(thscode,param,begintime,endtime,Callback,pUser,iD);
    
def THS_AsySpecial_StockLink(thscode,param,Callback,pUser,iD):
    return iFinD.FTQueryTHS_AsySpecial_StockLink(thscode,param,Callback,pUser,iD);
    
def THS_AsyrealTimeValuation(thscode,param,output,Callback,pUser,iD):
    thscodestr = thscode
    if(isinstance(thscode,list)):
        thscodestr = ",".join(thscode)
    return iFinD.FTQueryTHS_AsyrealTimeValuation(thscodestr,param,output,Callback,pUser,iD);
    
def THS_AsyReportQuery(thscode,param,output,Callback,pUser,iD):
    thscodestr = thscode
    if(isinstance(thscode,list)):
        thscodestr = ",".join(thscode)
    return iFinD.FTQueryTHS_AsyReportQuery(thscodestr,param,output,Callback,pUser,iD);
    
def THS_AsyfinalValuation(thscode,param,output,Callback,pUser,iD):
    thscodestr = thscode
    if(isinstance(thscode,list)):
        thscodestr = ",".join(thscode)
    return iFinD.FTQueryTHS_AsyfinalValuation(thscodestr,param,output,Callback,pUser,iD);
    
def THS_AsytoTHSCODE(transcontents,param,Callback,pUser,iD):
    return iFinD.FTQueryTHS_AsytoTHSCODE(transcontents,param,Callback,pUser,iD);

def THS_AsySpecial(type,thscode,param,Callback,pUser,iD):
    return iFinD.FTQueryTHS_AsySpecial(type,thscode,param,Callback,pUser,iD);

def THS_QuotesPushing(thscode,indicator="",Callback=None):
    thscodestr = thscode
    if(isinstance(thscode,list)):
        thscodestr = ",".join(thscode)
    return iFinD.FTQueryTHS_QuotesPushing(thscodestr,indicator,Callback)

def THS_UnQuotesPushing(thscode="",indicator=""):
    return iFinD.FTQueryTHS_UnQuotesPushing(thscode,indicator)   

def handle_params(encoding, params, **extra_params):
    if(iFinD.isless3):
        return params
    if not extra_params:
        return params
    if isinstance(params, bytes) : 
        try:
            params = params.decode(encoding)
        except:
            return params
    if isinstance(params, str) :
        params_dict = dict(item.split(':') for item in params.split(',') if ':' in item)
        
        extra_params_dict = {}
        for key, value in extra_params.items():
            if isinstance(value, dict):
                # 如果 value 是字典，则将其内容添加到 merged_params 中
                extra_params_dict.update(value)
            else:
                # 如果 value 不是字典，直接添加到 merged_params 中
                extra_params_dict[key] = value
        
        if 'format' in extra_params_dict:
            del extra_params_dict['format']
            
        params_dict.update(extra_params_dict)
        param_new = ','.join("{}:{}".format(key, value) for key,value in params_dict.items() if value)
        if len(param_new) == 0 :
            return params
        return param_new
            
    return params
        
def loads_str(data_str):
    import json 
    try:
        result = json.loads(data_str,object_pairs_hook=OrderedDict)
        return result
    except Exception as e:
        try:
            import re
            # 第一步：删除那些不属于合法转义序列的反斜杠
            # 合法转义字符列表: \" \\ \/ \b \f \n \r \t \uXXXX
            result = re.sub(r'\\(?!["\\/bfnrtu])', '', data_str)
            result = json.loads(result,object_pairs_hook=OrderedDict)
            return result
        except Exception as e:
            # 第二步：在双引号中的无效转义情况,对应命令：THS_BD('600843.SH','ths_stock_short_name_stock;ths_float_holder_name_stock',';2021-12-31,0','format:json')
            def replace_invalid_escapes(match):
                inner_str = match.group(1)
                # 移除无效的反斜杠（即保留有效的转义字符）
                return '"' + re.sub(r'\\(?!["\\/bfnrtu])', '', inner_str) + '"'

            # 使用正则表达式匹配双引号中的内容，并处理其中的无效转义
            result = re.sub(r'"(.*?)"', replace_invalid_escapes, result)
        
            try:
                # 再次尝试解析清理后的 JSON 字符串
                result = json.loads(result, object_pairs_hook=OrderedDict)
                return result
            except Exception as inner_e:
                print("Failed to parse JSON after cleaning: {}".format(inner_e))
                return None
            
def THS_Trans2DataFrame(data):
    import numpy as np,pandas as pd
    import json 
    dataframe = pd.DataFrame()
    
    if isinstance(data,dict):
        sData = json.dumps(data, ensure_ascii=False)
        if(iFinD.isless3):
            data= bytes(sData)
        else:
            data= bytes(sData,'utf8');
        out=iFinD.c_FTTransJson(data)
    else:
        out=iFinD.c_FTTransJson(data)       
        if(out is not None) and len(out)>0:
            out = out.decode(iFinD.decodeMethod,'ignore')
    if(out is not None) and len(out)>0:
        out=loads_str(out)
        dataframe = pd.DataFrame(out)
    return dataframe

def OnRealTimeCallback(pUderdata,id,sResult,len,errorcode,reserved):
    print(sResult)
    return 0

def OnFTAsynCallback(pUserdata,id,sResult,len,errorcode,reserved):
    global g_FunctionMgr
    global g_Funclock
    g_Funclock.acquire();
    userfunc = g_FunctionMgr[id]
    del(g_FunctionMgr[id])
    g_Funclock.release()
    if(callable(userfunc)):
        userfunc(pUserdata,id,sResult,len,errorcode,reserved)
    return 0

CMPTHSREALTIMEFUNC=CFUNCTYPE(c_int,c_void_p,c_int32,c_wchar_p,c_int32,c_int32,c_int32)

pRealTimeFunc=CMPTHSREALTIMEFUNC(OnRealTimeCallback)
pAsyFunc=CMPTHSREALTIMEFUNC(OnFTAsynCallback)
nRegRTID = 0;

g_FunctionMgr={};
g_Funclock=threading.Lock();

class iFinD:

    decodeMethod = "gb18030";
    isWin = 'Windows' in platform.system()
    version=sys.version  
    #print(version);
    verss=version.split()[0].split('.');
    ver=int(verss[0])+float(verss[1])/10;
    isless3 = True
    if(ver  >= 3.0):
        isless3 = False
    #sitepath=".";  
    try:
        #Python3
        import sysconfig
        sitepath = sysconfig.get_paths()["purelib"]
    except ImportError:
        #Python2
        from distutils.sysconfig import get_python_lib
        sitepath = get_python_lib()
    if(isWin):
        sitepath=sitepath+"\\iFinDPy.pth"
    else:
        sitepath=sitepath+"/iFinDPy.pth"
    print(sitepath)
    if(os.path.exists(sitepath)):
        pathfile=open(sitepath)
        dllpath=pathfile.readlines();
        pathfile.close();
        dllpath=''.join(dllpath).strip('\n')
        if(isWin):
            bit=int(sys.version.split(' bit ')[0].split()[-1]);
            if(bit==32 ):
                sitepath=dllpath+"\\ShellExport.dll"
            else:
                sitepath=dllpath+"\\ShellExport.dll"
        else:
            architecture = platform.architecture();
            if(architecture[0]== '32bit'):
                sitepath=dllpath+"/libShellExport.so";
            else:
                sitepath=dllpath+"/libShellExport.so";

    #print(sitepath)
  
    c_iFinDlib=cdll.LoadLibrary(sitepath)

    #FT_ifinDLoginPy
    c_FT_ifinDLoginPy=c_iFinDlib.THS_iFinDLoginPython;
    c_FT_ifinDLoginPy.restype=c_int32;
    c_FT_ifinDLoginPy.argtypes=[c_char_p,c_char_p]

    #FTQueryTHS_SynHFQByJsonPy
    c_FTQueryTHS_SynHFQByJsonPy=c_iFinDlib.THS_HighFrequenceSequencePython;
    c_FTQueryTHS_SynHFQByJsonPy.restype=c_void_p;
    c_FTQueryTHS_SynHFQByJsonPy.argtypes=[c_char_p,c_char_p,c_char_p,c_char_p,c_char_p]

    #FTQueryTHS_SynDateSeriesByJsonPy
    c_FTQueryTHS_SynDateSeriesByJsonPy=c_iFinDlib.THS_DateSequencePython;
    c_FTQueryTHS_SynDateSeriesByJsonPy.restype=c_void_p;
    c_FTQueryTHS_SynDateSeriesByJsonPy.argtypes=[c_char_p,c_char_p,c_char_p,c_char_p,c_char_p]

    #c_FTQuery_SynSnapshotPy
    c_FTQuery_SynSnapshotPy=c_iFinDlib.THS_SnapshotPython;
    c_FTQuery_SynSnapshotPy.restype=c_void_p;
    c_FTQuery_SynSnapshotPy.argtypes=[c_char_p,c_char_p,c_char_p,c_char_p,c_char_p]

    #c_FTQuery_SynDateSerialPy
    c_FTQuery_SynTHS_DateSerialPython=c_iFinDlib.THS_DateSerialPython;
    c_FTQuery_SynTHS_DateSerialPython.restype=c_void_p;
    c_FTQuery_SynTHS_DateSerialPython.argtypes=[c_char_p,c_char_p,c_char_p,c_char_p,c_char_p,c_char_p]

    #FTQuery_SynRTByJsonPy
    c_FTQuery_SynRTByJsonPy=c_iFinDlib.FTQuery_SynRTByJsonPy;
    c_FTQuery_SynRTByJsonPy.restype=c_char_p;
    c_FTQuery_SynRTByJsonPy.argtypes=[c_wchar_p,c_wchar_p,c_wchar_p]

    #FTQuery_SynBasicDataPy
    c_FTQuery_SynBasicDataPy=c_iFinDlib.FTQuery_SynBasicDataPy;
    c_FTQuery_SynBasicDataPy.restype=c_char_p;
    c_FTQuery_SynBasicDataPy.argtypes=[c_wchar_p,c_wchar_p]

    #FTQuery_SynDataPoolByJsonPy
    c_FTQuery_SynDataPoolByJsonPy=c_iFinDlib.FTQuery_SynDatapool;
    c_FTQuery_SynDataPoolByJsonPy.restype=c_char_p;
    c_FTQuery_SynDataPoolByJsonPy.argtypes=[c_wchar_p,c_wchar_p,c_wchar_p]

    #FTQuery_SynHisQuoteByJsonPy
    c_FTQuery_SynHisQuoteByJsonPy=c_iFinDlib.FTQuery_SynHisQuoteByJsonPy;
    c_FTQuery_SynHisQuoteByJsonPy.restype=c_char_p;
    c_FTQuery_SynHisQuoteByJsonPy.argtypes=[c_wchar_p,c_wchar_p,c_wchar_p,c_wchar_p,c_wchar_p]

    #c_FTQuery_SynDateSerialByJsonPy=c_iFinDlib.FTQuery_SynDateSerialByJsonPy;
    #c_FTQuery_SynDateSerialByJsonPy.restype=c_char_p;
    #c_FTQuery_SynDateSerialByJsonPy.argtypes=[c_wchar_p,c_wchar_p,c_wchar_p,c_wchar_p,c_wchar_p,c_wchar_p]

    #FTQueryTHS_SynRTByJsonPy
    c_FTQueryTHS_SynRTByJsonPy=c_iFinDlib.THS_RealtimeQuotesPython;
    c_FTQueryTHS_SynRTByJsonPy.restype=c_void_p;
    c_FTQueryTHS_SynRTByJsonPy.argtypes=[c_char_p,c_char_p,c_char_p]

    #FTQueryTHS_SynBasicDataPy
    c_FTQueryTHS_SynBasicDataPy=c_iFinDlib.THS_BasicDataPython;
    c_FTQueryTHS_SynBasicDataPy.restype=c_void_p;
    c_FTQueryTHS_SynBasicDataPy.argtypes=[c_char_p,c_char_p,c_char_p]
    
    #FTQueryTHS_SynSpecial_ShapePredictPy
    c_FTQueryTHS_SynSpecial_ShapePredictPy=c_iFinDlib.THS_Special_ShapePredictPython;
    c_FTQueryTHS_SynSpecial_ShapePredictPy.restype=c_void_p;
    c_FTQueryTHS_SynSpecial_ShapePredictPy.argtypes=[c_char_p,c_char_p,c_char_p,c_char_p]
    
    #FTQueryTHS_SynSpecial_StockLinkPy
    c_FTQueryTHS_SynSpecial_StockLinkPy=c_iFinDlib.THS_Special_StockLinkPython;
    c_FTQueryTHS_SynSpecial_StockLinkPy.restype=c_void_p;
    c_FTQueryTHS_SynSpecial_StockLinkPy.argtypes=[c_char_p,c_char_p]
    
    #FTQueryTHS_SynrealTimeValuationPy
    c_FTQueryTHS_SynrealTimeValuationPy=c_iFinDlib.THS_realTimeValuationPython;
    c_FTQueryTHS_SynrealTimeValuationPy.restype=c_void_p;
    c_FTQueryTHS_SynrealTimeValuationPy.argtypes=[c_char_p,c_char_p,c_char_p]
    
    #FTQueryTHS_SynfinalValuationPy
    c_FTQueryTHS_SynfinalValuationPy=c_iFinDlib.THS_finalValuationPython;
    c_FTQueryTHS_SynfinalValuationPy.restype=c_void_p;
    c_FTQueryTHS_SynfinalValuationPy.argtypes=[c_char_p,c_char_p,c_char_p]
    
    #FTQueryTHS_SynReportQueryPy
    c_FTQueryTHS_SynReportQueryPy=c_iFinDlib.THS_ReportQueryPython;
    c_FTQueryTHS_SynReportQueryPy.restype=c_void_p;
    c_FTQueryTHS_SynReportQueryPy.argtypes=[c_char_p,c_char_p,c_char_p]
    
    #FTQueryTHS_SyntoTHSCODEPy
    c_FTQueryTHS_SyntoTHSCODEPy=c_iFinDlib.THS_toTHSCODEPython;
    c_FTQueryTHS_SyntoTHSCODEPy.restype=c_void_p;
    c_FTQueryTHS_SyntoTHSCODEPy.argtypes=[c_char_p,c_char_p]
    
    #FTQueryTHS_SynSpecial_Py
    c_FTQueryTHS_SynSpecial_Py=c_iFinDlib.THS_Special_Python;
    c_FTQueryTHS_SynSpecial_Py.restype=c_void_p;
    c_FTQueryTHS_SynSpecial_Py.argtypes=[c_char_p,c_char_p,c_char_p]

    #FTQueryTHS_SynDataPoolByJsonPy
    c_FTQueryTHS_SynDataPoolByJsonPy=c_iFinDlib.THS_DataPoolPython;
    c_FTQueryTHS_SynDataPoolByJsonPy.restype=c_void_p;
    c_FTQueryTHS_SynDataPoolByJsonPy.argtypes=[c_char_p,c_char_p,c_char_p]
    
    #FTQueryTHS_SynDRByJsonPy
    c_FTQueryTHS_SynDRByJsonPy=c_iFinDlib.THS_DRPython;
    c_FTQueryTHS_SynDRByJsonPy.restype=c_void_p;
    c_FTQueryTHS_SynDRByJsonPy.argtypes=[c_char_p,c_char_p,c_char_p]
    
    #FTQueryTHS_SynRPTByJsonPy
    c_FTQueryTHS_SynRPTByJsonPy=c_iFinDlib.THS_RPTPython;
    c_FTQueryTHS_SynRPTByJsonPy.restype=c_void_p;
    c_FTQueryTHS_SynRPTByJsonPy.argtypes=[c_char_p,c_char_p,c_char_p,c_char_p]
    
    #FTQueryTHS_SynFEBByJsonPy
    c_FTQueryTHS_SynFEBByJsonPy=c_iFinDlib.THS_FEBPython;
    c_FTQueryTHS_SynFEBByJsonPy.restype=c_void_p;
    c_FTQueryTHS_SynFEBByJsonPy.argtypes=[c_char_p,c_char_p]
    
    #FTQueryTHS_SyniResearchByJsonPy
    c_FTQueryTHS_SyniResearchByJsonPy=c_iFinDlib.THS_iResearchPython;
    c_FTQueryTHS_SyniResearchByJsonPy.restype=c_void_p;
    c_FTQueryTHS_SyniResearchByJsonPy.argtypes=[c_char_p,c_char_p,c_char_p]
    
    #FTQueryTHS_SyniEventByJsonPy
    c_FTQueryTHS_SyniEventByJsonPy=c_iFinDlib.THS_iEventPython;
    c_FTQueryTHS_SyniEventByJsonPy.restype=c_void_p;
    c_FTQueryTHS_SyniEventByJsonPy.argtypes=[c_char_p,c_char_p,c_char_p]
    
    #FTQueryTHS_SyniTranslateByJsonPy
    c_FTQueryTHS_SyniTranslateByJsonPy=c_iFinDlib.THS_iTranslatePython;
    c_FTQueryTHS_SyniTranslateByJsonPy.restype=c_void_p;
    c_FTQueryTHS_SyniTranslateByJsonPy.argtypes=[c_char_p,c_char_p,c_char_p]

    #FTQueryTHS_SynHisQuoteByJsonPy
    c_FTQueryTHS_SynHisQuoteByJsonPy=c_iFinDlib.THS_HistoryQuotesPython;
    c_FTQueryTHS_SynHisQuoteByJsonPy.restype=c_void_p;
    c_FTQueryTHS_SynHisQuoteByJsonPy.argtypes=[c_char_p,c_char_p,c_char_p,c_char_p,c_char_p]

    #FTQueryTHS_SynHDByJsonPy
    c_FTQueryTHS_SynHDByJsonPy=c_iFinDlib.THS_HDPython;
    c_FTQueryTHS_SynHDByJsonPy.restype=c_void_p;
    c_FTQueryTHS_SynHDByJsonPy.argtypes=[c_char_p,c_char_p,c_char_p,c_char_p,c_char_p]

    #FT_ifinDLogoutPy
    c_FT_ifinDLogoutPy=c_iFinDlib.THS_ifinDLogoutPython;
    c_FT_ifinDLogoutPy.restype=c_int32;
    c_FT_ifinDLogoutPy.argtypes=[]
    
    #FT_SetLanguagePy
    c_FT_SetLanguagePy=c_iFinDlib.THS_SetLanguagePython;
    c_FT_SetLanguagePy.restype=c_int32;
    c_FT_SetLanguagePy.argtypes=[c_int32]

    #FT_EDBQuery
    C_FT_ifinDEDBQuery=c_iFinDlib.THS_EDBQueryPython;
    C_FT_ifinDEDBQuery.restype=c_void_p;
    C_FT_ifinDEDBQuery.argtypes=[c_char_p,c_char_p,c_char_p]
    
    #FT_EDB
    C_FT_ifinDEDB=c_iFinDlib.THS_EDBPython;
    C_FT_ifinDEDB.restype=c_void_p;
    C_FT_ifinDEDB.argtypes=[c_char_p,c_char_p,c_char_p,c_char_p]

    #FT_iwencai
    C_FT_ifinDiwencai=c_iFinDlib.THS_iwencaiPython;
    C_FT_ifinDiwencai.restype=c_void_p;
    C_FT_ifinDiwencai.argtypes=[c_char_p,c_char_p]
    
    #FT_WCQuery
    C_FT_ifinDWCQuery=c_iFinDlib.THS_WCQueryPython;
    C_FT_ifinDWCQuery.restype=c_void_p;
    C_FT_ifinDWCQuery.argtypes=[c_char_p,c_char_p]

    #FTQueryTHS_DateSerialPy
    c_FTQueryTHS_THS_AsyDateSerialPython=c_iFinDlib.THS_AsyDateSerialPython;
    c_FTQueryTHS_THS_AsyDateSerialPython.restype=c_int32;
    c_FTQueryTHS_THS_AsyDateSerialPython.argtypes=[c_char_p,c_char_p,c_char_p,c_char_p,c_char_p,c_char_p,CMPTHSREALTIMEFUNC,c_void_p,POINTER(c_int32)];
    
    #FTQueryTHS_AsySpecial_ShapePredictPy
    c_FTQueryTHS_AsySpecial_ShapePredictPy=c_iFinDlib.THS_AsySpecial_ShapePredictPython;
    c_FTQueryTHS_AsySpecial_ShapePredictPy.restype=c_int32;
    c_FTQueryTHS_AsySpecial_ShapePredictPy.argtypes=[c_char_p,c_char_p,c_char_p,c_char_p,CMPTHSREALTIMEFUNC,c_void_p,POINTER(c_int32)];
    
    #FTQueryTHS_AsySpecial_StockLinkPy
    c_FTQueryTHS_AsySpecial_StockLinkPy=c_iFinDlib.THS_AsySpecial_StockLinkPython;
    c_FTQueryTHS_AsySpecial_StockLinkPy.restype=c_int32;
    c_FTQueryTHS_AsySpecial_StockLinkPy.argtypes=[c_char_p,c_char_p,CMPTHSREALTIMEFUNC,c_void_p,POINTER(c_int32)];
    
    #FTQueryTHS_AsyrealTimeValuationPy
    c_FTQueryTHS_AsyrealTimeValuationPy=c_iFinDlib.THS_AsyrealTimeValuationPython;
    c_FTQueryTHS_AsyrealTimeValuationPy.restype=c_int32;
    c_FTQueryTHS_AsyrealTimeValuationPy.argtypes=[c_char_p,c_char_p,c_char_p,CMPTHSREALTIMEFUNC,c_void_p,POINTER(c_int32)];
    
    #FTQueryTHS_AsyfinalValuationPy
    c_FTQueryTHS_AsyfinalValuationPy=c_iFinDlib.THS_AsyfinalValuationPython;
    c_FTQueryTHS_AsyfinalValuationPy.restype=c_int32;
    c_FTQueryTHS_AsyfinalValuationPy.argtypes=[c_char_p,c_char_p,c_char_p,CMPTHSREALTIMEFUNC,c_void_p,POINTER(c_int32)];
    
    #FTQueryTHS_AsyReportQueryPy
    c_FTQueryTHS_AsyReportQueryPy=c_iFinDlib.THS_AsyReportQueryPython;
    c_FTQueryTHS_AsyReportQueryPy.restype=c_int32;
    c_FTQueryTHS_AsyReportQueryPy.argtypes=[c_char_p,c_char_p,c_char_p,CMPTHSREALTIMEFUNC,c_void_p,POINTER(c_int32)];
    
    #FTQueryTHS_AsytoTHSCODEPy
    c_FTQueryTHS_AsytoTHSCODEPy=c_iFinDlib.THS_AsytoTHSCODEPython;
    c_FTQueryTHS_AsytoTHSCODEPy.restype=c_int32;
    c_FTQueryTHS_AsytoTHSCODEPy.argtypes=[c_char_p,c_char_p,CMPTHSREALTIMEFUNC,c_void_p,POINTER(c_int32)];
    
    #FTQueryTHS_AsySpecial_Py
    c_FTQueryTHS_AsySpecial_Py=c_iFinDlib.THS_AsySpecial_Python;
    c_FTQueryTHS_AsySpecial_Py.restype=c_int32;
    c_FTQueryTHS_AsySpecial_Py.argtypes=[c_char_p,c_char_p,c_char_p,CMPTHSREALTIMEFUNC,c_void_p,POINTER(c_int32)];

    #FTQueryTHS_AsynRTByJsonPy
    C_FTQueryTHS_AsynRTByJsonPy=c_iFinDlib.THS_QuotesPushingPython;
    C_FTQueryTHS_AsynRTByJsonPy.restype=c_int32;
    C_FTQueryTHS_AsynRTByJsonPy.argtypes=[c_char_p,c_char_p,c_char_p,c_bool,CMPTHSREALTIMEFUNC,c_void_p,POINTER(c_int32)]

    #FTQueryTHS_HighFrequenceSequencePy
    c_FTQueryTHS_HighFrequenceSequencePy=c_iFinDlib.THS_AsyHighFrequenceSequencePython;
    c_FTQueryTHS_HighFrequenceSequencePy.restype=c_int32;
    c_FTQueryTHS_HighFrequenceSequencePy.argtypes=[c_char_p,c_char_p,c_char_p,c_char_p,c_char_p,CMPTHSREALTIMEFUNC,c_void_p,POINTER(c_int32)];

    #FTQueryTHS_DateSequencePy
    c_FTQueryTHS_DateSequencePy=c_iFinDlib.THS_AsyDateSequencePython;
    c_FTQueryTHS_DateSequencePy.restype=c_int32;
    c_FTQueryTHS_DateSequencePy.argtypes=[c_char_p,c_char_p,c_char_p,c_char_p,c_char_p,CMPTHSREALTIMEFUNC,c_void_p,POINTER(c_int32)]

    #FTQueryTHS_SnapshotPy
    c_FTQueryTHS_SnapshotPy=c_iFinDlib.THS_AsySnapshotPython;
    c_FTQueryTHS_SnapshotPy.restype=c_int32;
    c_FTQueryTHS_SnapshotPy.argtypes=[c_char_p,c_char_p,c_char_p,c_char_p,c_char_p,CMPTHSREALTIMEFUNC,c_void_p,POINTER(c_int32)]

    #FTQueryTHS_RealtimeQuotesPy
    c_FTQueryTHS_RealtimeQuotesPy=c_iFinDlib.THS_AsyRealtimeQuotesPython;
    c_FTQueryTHS_RealtimeQuotesPy.restype=c_int32;
    c_FTQueryTHS_RealtimeQuotesPy.argtypes=[c_char_p,c_char_p,c_char_p,c_bool,CMPTHSREALTIMEFUNC,c_void_p,POINTER(c_int32)]

    #FTQuerySynTHS_iwencaiPy
    c_FTQueryTHS_iwencaiPy=c_iFinDlib.THS_AsyiwencaiPython;
    c_FTQueryTHS_iwencaiPy.restype=c_int32;
    c_FTQueryTHS_iwencaiPy.argtypes=[c_char_p,c_char_p,CMPTHSREALTIMEFUNC,c_void_p,POINTER(c_int32)]
    
    #FTQuerySynTHS_WCQueryPy
    c_FTQueryTHS_WCQueryPy=c_iFinDlib.THS_AsyWCQueryPython;
    c_FTQueryTHS_WCQueryPy.restype=c_int32;
    c_FTQueryTHS_WCQueryPy.argtypes=[c_char_p,c_char_p,CMPTHSREALTIMEFUNC,c_void_p,POINTER(c_int32)]

    #FTQueryTHS_BasicDataPy
    c_FTQueryTHS_BasicDataPy=c_iFinDlib.THS_AsyBasicDataPython;
    c_FTQueryTHS_BasicDataPy.restype=c_int32;
    c_FTQueryTHS_BasicDataPy.argtypes=[c_char_p,c_char_p,c_char_p,CMPTHSREALTIMEFUNC,c_void_p,POINTER(c_int32)]

    #FTQueryTHS_DatapoolPy
    c_FTQueryTHS_DatapoolPy=c_iFinDlib.THS_AsyDataPoolPython;
    c_FTQueryTHS_DatapoolPy.restype=c_int32;
    c_FTQueryTHS_DatapoolPy.argtypes=[c_char_p,c_char_p,c_char_p,CMPTHSREALTIMEFUNC,c_void_p,POINTER(c_int32)]
    
    #FTQueryTHS_DRPy
    c_FTQueryTHS_DRPy=c_iFinDlib.THS_AsyDRPython;
    c_FTQueryTHS_DRPy.restype=c_int32;
    c_FTQueryTHS_DRPy.argtypes=[c_char_p,c_char_p,c_char_p,CMPTHSREALTIMEFUNC,c_void_p,POINTER(c_int32)]
    
    #FTQueryTHS_RPTPy
    c_FTQueryTHS_RPTPy=c_iFinDlib.THS_AsyRPTPython;
    c_FTQueryTHS_RPTPy.restype=c_int32;
    c_FTQueryTHS_RPTPy.argtypes=[c_char_p,c_char_p,c_char_p,c_char_p,CMPTHSREALTIMEFUNC,c_void_p,POINTER(c_int32)]
    
    #FTQueryTHS_FEBPy
    c_FTQueryTHS_FEBPy=c_iFinDlib.THS_AsyFEBPython;
    c_FTQueryTHS_FEBPy.restype=c_int32;
    c_FTQueryTHS_FEBPy.argtypes=[c_char_p,c_char_p,CMPTHSREALTIMEFUNC,c_void_p,POINTER(c_int32)]
    
    #FTQueryTHS_iResearchPy
    c_FTQueryTHS_iResearchPy=c_iFinDlib.THS_AsyiResearchPython;
    c_FTQueryTHS_iResearchPy.restype=c_int32;
    c_FTQueryTHS_iResearchPy.argtypes=[c_char_p,c_char_p,c_char_p,CMPTHSREALTIMEFUNC,c_void_p,POINTER(c_int32)]
    
    #FTQueryTHS_iEventPy
    c_FTQueryTHS_iEventPy=c_iFinDlib.THS_AsyiEventPython;
    c_FTQueryTHS_iEventPy.restype=c_int32;
    c_FTQueryTHS_iEventPy.argtypes=[c_char_p,c_char_p,c_char_p,CMPTHSREALTIMEFUNC,c_void_p,POINTER(c_int32)]
    
    #FTQueryTHS_iTranslatePy
    c_FTQueryTHS_iTranslatePy=c_iFinDlib.THS_AsyiTranslatePython;
    c_FTQueryTHS_iTranslatePy.restype=c_int32;
    c_FTQueryTHS_iTranslatePy.argtypes=[c_char_p,c_char_p,c_char_p,CMPTHSREALTIMEFUNC,c_void_p,POINTER(c_int32)]

    #FTQueryTHS_HisQuotePy
    c_FTQueryTHS_HisQuotePy=c_iFinDlib.THS_AsyHistoryQuotesPython;
    c_FTQueryTHS_HisQuotePy.restype=c_int32;
    c_FTQueryTHS_HisQuotePy.argtypes=[c_char_p,c_char_p,c_char_p,c_char_p,c_char_p,CMPTHSREALTIMEFUNC,c_void_p,POINTER(c_int32)]

    #FTQueryTHS_EDBQueryPy
    c_FTQueryTHS_EDBQueryPy=c_iFinDlib.THS_AsyEDBQueryPython;
    c_FTQueryTHS_EDBQueryPy.restype=c_int32;
    c_FTQueryTHS_EDBQueryPy.argtypes=[c_char_p,c_char_p,c_char_p,CMPTHSREALTIMEFUNC,c_void_p,POINTER(c_int32)]
    
    #FTQueryTHS_EDBPy
    c_FTQueryTHS_EDBPy=c_iFinDlib.THS_AsyEDBPython;
    c_FTQueryTHS_EDBPy.restype=c_int32;
    c_FTQueryTHS_EDBPy.argtypes=[c_char_p,c_char_p,c_char_p,c_char_p,CMPTHSREALTIMEFUNC,c_void_p,POINTER(c_int32)]

    #SetValue
    c_SetValue=c_iFinDlib.SetValue;
    c_SetValue.restype=c_int;
    c_SetValue.argtypes=[c_int,POINTER(c_int)]

    #DeleteMm
    c_DeleteMm=c_iFinDlib.DeleteMemory;
    c_DeleteMm.restype=c_int;
    c_DeleteMm.argtypes=[c_void_p];

    #FT_DataStatistics
    C_FT_ifinDDataStatissticsPy=c_iFinDlib.THS_DataStatisticsPython;
    C_FT_ifinDDataStatissticsPy.restype=c_void_p;
    C_FT_ifinDDataStatissticsPy.argtypes=[]

    #FT_GetErrorMsg
    C_FT_ifinDErrorMsg=c_iFinDlib.THS_GetErrorInfoPython;
    C_FT_ifinDErrorMsg.restype=c_void_p;
    C_FT_ifinDErrorMsg.argtypes=[c_int32];

    #FTQueryTHS_SynDateQueryPy
    C_FT_ifinDDateQuery=c_iFinDlib.THS_DateQueryPython;
    C_FT_ifinDDateQuery.restype=c_void_p;
    C_FT_ifinDDateQuery.argtypes=[c_char_p,c_char_p,c_char_p,c_char_p]
    
    #FTQueryTHS_SynDatequeryPy (新)
    C_FT_ifinDDate_Query=c_iFinDlib.THS_Date_QueryPython;
    C_FT_ifinDDate_Query.restype=c_void_p;
    C_FT_ifinDDate_Query.argtypes=[c_char_p,c_char_p,c_char_p,c_char_p]

    #FTQueryTHS_SynDateOffsetPy
    C_FT_ifinDDateOffset=c_iFinDlib.THS_DateOffsetPython;
    C_FT_ifinDDateOffset.restype=c_void_p;
    C_FT_ifinDDateOffset.argtypes=[c_char_p,c_char_p,c_char_p]
    
    #FTQueryTHS_SynDateoffsetPy (新)
    C_FT_ifinDDate_Offset=c_iFinDlib.THS_Date_OffsetPython;
    C_FT_ifinDDate_Offset.restype=c_void_p;
    C_FT_ifinDDate_Offset.argtypes=[c_char_p,c_char_p,c_char_p]

    #FTQueryTHS_SynDateCountPy
    C_FT_ifinDDateCount=c_iFinDlib.THS_DateCountPython;
    C_FT_ifinDDateCount.restype=c_void_p;
    C_FT_ifinDDateCount.argtypes=[c_char_p,c_char_p,c_char_p,c_char_p]

    #FTQuery_SynHFQByJsonPy
    c_FTQuery_SynHFQByJsonPy=c_iFinDlib.FTQuery_SynHFQByJsonPy;
    c_FTQuery_SynHFQByJsonPy.restype=c_char_p;
    c_FTQuery_SynHFQByJsonPy.argtypes=[c_wchar_p,c_wchar_p,c_wchar_p,c_wchar_p,c_wchar_p]

    #FTQuery_SynDateSeriesByJsonPy
    c_FTQuery_SynDateSeriesByJsonPy=c_iFinDlib.FTQuery_SynDateSeriesByJsonPy;
    c_FTQuery_SynDateSeriesByJsonPy.restype=c_char_p;
    c_FTQuery_SynDateSeriesByJsonPy.argtypes=[c_wchar_p,c_wchar_p,c_wchar_p,c_wchar_p,c_wchar_p]
    
    #FTTransJson
    c_FTTransJson=c_iFinDlib.THS_TransJSONPython;
    c_FTTransJson.restype=c_char_p;
    c_FTTransJson.argtypes=[c_char_p]

    @staticmethod
    def FT_iFinDLogin(username,password):
        """登陆入口函数"""
        if(iFinD.isWin):
            if(iFinD.isless3):
                username=c_char_p(username);
                password=c_char_p(password);
            else:
                username=c_char_p(bytes(username,'gbk'));
                password=c_char_p(bytes(password,'gbk'));
        else:
            username=c_char_p(bytes(username,'utf8'));
            password=c_char_p(bytes(password,'utf8'));
        out=iFinD.c_FT_ifinDLoginPy(username.value,password.value);
        return out;
    #FT_ifinDLoginPy=staticmethod(FT_ifinDLoginPy)

    @staticmethod
    def FT_iFinDLogout():
         """登出入口函数"""
         out=iFinD.c_FT_ifinDLogoutPy();
         return out;
     #FT_ifinDLogoutPy=staticmethod(FT_ifinDLogoutPy)
     
    @staticmethod
    def FT_SetLanguage(language):
         """设置语言函数"""
         out=iFinD.c_FT_SetLanguagePy(language);
         return out;

    @staticmethod
    def FTQuerySyn_HighFrequenceSequence(thscode,jsonIndicator,jsonparam,begintime,endtime):
        import json
        """高频序列"""
        thscode=c_wchar_p(thscode);
        jsonIndicators=c_wchar_p(jsonIndicator);
        jsonparams=c_wchar_p(jsonparam);
        begintime=c_wchar_p(begintime);
        endtime=c_wchar_p(endtime);
        out=iFinD.c_FTQuery_SynHFQByJsonPy(thscode.value,jsonIndicators.value,jsonparams.value,begintime.value,endtime.value);
        out=json.loads(out.decode(iFinD.decodeMethod));
        return out;

    @staticmethod    
    def FTQuerySynTHS_HighFrequenceSequence(thscode,jsonIndicator,jsonparam,begintime,endtime,outflag=False):
        import json
        """高频序列"""
        if(iFinD.isWin):
            if(iFinD.isless3):
                thscode=c_char_p(thscode);
                jsonIndicators=c_char_p(jsonIndicator);
                jsonparams=c_char_p(jsonparam);
                begintime=c_char_p(begintime);
                endtime=c_char_p(endtime);
            else:
                thscode=c_char_p(bytes(thscode,'gbk'));
                jsonIndicators=c_char_p(bytes(jsonIndicator,'gbk'));
                jsonparams=c_char_p(bytes(jsonparam,'gbk'));
                begintime=c_char_p(bytes(begintime,'gbk'));
                endtime=c_char_p(bytes(endtime,'gbk'));
        else:
            thscode=c_char_p(bytes(thscode,'utf8'));
            jsonIndicators=c_char_p(bytes(jsonIndicator,'utf8'));
            jsonparams=c_char_p(bytes(jsonparam,'utf8'));
            begintime=c_char_p(bytes(begintime,'utf8'));
            endtime=c_char_p(bytes(endtime,'utf8'));
        ptr=iFinD.c_FTQueryTHS_SynHFQByJsonPy(thscode.value,jsonIndicators.value,jsonparams.value,begintime.value,endtime.value);
        out = cast(ptr,c_char_p).value
        if outflag == False:
            out=json.loads(out.decode(iFinD.decodeMethod),object_pairs_hook=OrderedDict);
        iFinD.c_DeleteMm(ptr);
        return out;
        
    @staticmethod    
    def FTQuerySynTHS_HF(thscode,jsonIndicator,jsonparam,begintime,endtime,format='format:dataframe'):
        """高频序列(新)"""
        if(iFinD.isWin):
            if(iFinD.isless3):
                thscode=c_char_p(thscode);
                jsonIndicators=c_char_p(jsonIndicator);
                jsonparams=c_char_p(jsonparam);
                begintime=c_char_p(begintime);
                endtime=c_char_p(endtime);
            else:
                thscode=c_char_p(bytes(thscode,'gbk'));
                jsonIndicators=c_char_p(bytes(jsonIndicator,'gbk'));
                jsonparams=c_char_p(bytes(jsonparam,'gbk'));
                begintime=c_char_p(bytes(begintime,'gbk'));
                endtime=c_char_p(bytes(endtime,'gbk'));
        else:
            thscode=c_char_p(bytes(thscode,'utf8'));
            jsonIndicators=c_char_p(bytes(jsonIndicator,'utf8'));
            jsonparams=c_char_p(bytes(jsonparam,'utf8'));
            begintime=c_char_p(bytes(begintime,'utf8'));
            endtime=c_char_p(bytes(endtime,'utf8'));
        ptr=iFinD.c_FTQueryTHS_SynHFQByJsonPy(thscode.value,jsonIndicators.value,jsonparams.value,begintime.value,endtime.value);
        result = cast(ptr,c_char_p).value
        data = THSData()
        indicator = jsonIndicator.split(';')
        data.indicators = indicator
        data.formatResult(result,format)
        iFinD.c_DeleteMm(ptr);
        return data;
    
    @staticmethod
    def FTQuerySyn_DateSequence(thscode,jsonIndicator,jsonparam,begintime,endtime):
        import json
        """日期序列"""
        thscode=c_wchar_p(thscode);
        jsonIndicators=c_wchar_p(jsonIndicator);
        jsonparams=c_wchar_p(jsonparam);
        begintime=c_wchar_p(begintime);
        endtime=c_wchar_p(endtime);
        out=iFinD.c_FTQuery_SynDateSeriesByJsonPy(thscode.value,jsonIndicators.value,jsonparams.value,begintime.value,endtime.value);
        out=json.loads(out.decode(iFinD.decodeMethod));
        return out;

    @staticmethod
    def FTQuerySynTHS_DateSequence(thscode,jsonIndicator,jsonparam,begintime,endtime,outflag=False):
        import json
        """日期序列"""
        if(iFinD.isWin):
            if(iFinD.isless3):
                thscode=c_char_p(thscode);
                jsonIndicators=c_char_p(jsonIndicator);
                jsonparams=c_char_p(jsonparam);
                begintime=c_char_p(begintime);
                endtime=c_char_p(endtime);
            else:
                thscode=c_char_p(bytes(thscode,'gbk'));
                jsonIndicators=c_char_p(bytes(jsonIndicator,'gbk'));
                jsonparams=c_char_p(bytes(jsonparam,'gbk'));
                begintime=c_char_p(bytes(begintime,'gbk'));
                endtime=c_char_p(bytes(endtime,'gbk'));
        else:
            thscode=c_char_p(bytes(thscode,'utf8'));
            jsonIndicators=c_char_p(bytes(jsonIndicator,'utf8'));
            jsonparams=c_char_p(bytes(jsonparam,'utf8'));
            begintime=c_char_p(bytes(begintime,'utf8'));
            endtime=c_char_p(bytes(endtime,'utf8'));
        ptr=iFinD.c_FTQueryTHS_SynDateSeriesByJsonPy(thscode.value,jsonIndicators.value,jsonparams.value,begintime.value,endtime.value);
        out = cast(ptr,c_char_p).value
        if outflag == False:
            out=json.loads(out.decode(iFinD.decodeMethod),object_pairs_hook=OrderedDict);
        iFinD.c_DeleteMm(ptr);
        return out;

    @staticmethod
    def FTQuerySyn_RealtimeQuotes(thscode,jsonIndicator,jsonparam):
        import json
        """实时行情"""
        thscode=c_wchar_p(thscode);
        jsonIndicators=c_wchar_p(jsonIndicator);
        jsonparams=c_wchar_p(jsonparam);
        out=iFinD.c_FTQuery_SynRTByJsonPy(thscode.value,jsonIndicators.value,jsonparams.value);
        out=json.loads(out.decode(iFinD.decodeMethod));
        return out;

    @staticmethod
    def FTQuerySynTHS_RealtimeQuotes(thscode,jsonIndicator,jsonparam,outflag=False):
        import json
        """实时行情"""
        if(iFinD.isWin):
            if(iFinD.isless3):
                thscode=c_char_p(thscode);
                jsonIndicators=c_char_p(jsonIndicator);
                jsonparams=c_char_p(jsonparam);
            else:
                thscode=c_char_p(bytes(thscode,'gbk'));
                jsonIndicators=c_char_p(bytes(jsonIndicator,'gbk'));
                jsonparams=c_char_p(bytes(jsonparam,'gbk'));
        else:
            thscode=c_char_p(bytes(thscode,'utf8'));
            jsonIndicators=c_char_p(bytes(jsonIndicator,'utf8'));
            jsonparams=c_char_p(bytes(jsonparam,'utf8'));
        ptr=iFinD.c_FTQueryTHS_SynRTByJsonPy(thscode.value,jsonIndicators.value,jsonparams.value);
        out = cast(ptr,c_char_p).value
        if outflag == False:
            out=json.loads(out.decode(iFinD.decodeMethod),object_pairs_hook=OrderedDict);
        iFinD.c_DeleteMm(ptr);
        return out;
        
    @staticmethod
    def FTQuerySynTHS_RQ(thscode,jsonIndicator,jsonparam,format='format:dataframe'):
        """实时行情(新)"""
        if(iFinD.isWin):
            if(iFinD.isless3):
                thscode=c_char_p(thscode);
                jsonIndicators=c_char_p(jsonIndicator);
                jsonparams=c_char_p(jsonparam);
            else:
                thscode=c_char_p(bytes(thscode,'gbk'));
                jsonIndicators=c_char_p(bytes(jsonIndicator,'gbk'));
                jsonparams=c_char_p(bytes(jsonparam,'gbk'));
        else:
            thscode=c_char_p(bytes(thscode,'utf8'));
            jsonIndicators=c_char_p(bytes(jsonIndicator,'utf8'));
            jsonparams=c_char_p(bytes(jsonparam,'utf8'));
        ptr=iFinD.c_FTQueryTHS_SynRTByJsonPy(thscode.value,jsonIndicators.value,jsonparams.value);
        result = cast(ptr,c_char_p).value
        data = THSData()
        indicator = jsonIndicator.split(';')
        data.indicators = indicator
        data.formatResult(result,format)
        iFinD.c_DeleteMm(ptr);
        return data;

    @staticmethod
    def FTQuerySyn_BasicData(Indicatorname,paramname):
        import json
        """基础数据"""
        indicator=c_wchar_p(Indicatorname);
        params=c_wchar_p(paramname);
        out=iFinD.c_FTQuery_SynBasicDataPy(indicator.value,params.value);
        out=json.loads(out.decode(iFinD.decodeMethod));
        return out;

    @staticmethod
    def FTQuerySynTHS_BasicData(code,Indicatorname,paramname,outflag=False):
        import json
        """基础数据"""
        if(iFinD.isWin):
            if(iFinD.isless3):
                codes=c_char_p(code)
                indicator=c_char_p(Indicatorname);
                params=c_char_p(paramname);
            else:
                codes=c_char_p(bytes(code,'gbk'))
                indicator=c_char_p(bytes(Indicatorname,'gbk'));
                params=c_char_p(bytes(paramname,'gbk'));
        else:
            codes=c_char_p(bytes(code,'utf8'))
            indicator=c_char_p(bytes(Indicatorname,'utf8'));
            params=c_char_p(bytes(paramname,'utf8'));
        ptr=iFinD.c_FTQueryTHS_SynBasicDataPy(codes.value,indicator.value,params.value);
        out = cast(ptr,c_char_p).value
        if outflag == False:
            out = out.decode(iFinD.decodeMethod,'ignore')
            if len(out) > 0:
                out=loads_str(out)
        iFinD.c_DeleteMm(ptr);
        return out;
        
    @staticmethod
    def FTQuerySynTHS_BD(code,Indicatorname,paramname,format='format:dataframe'):
        """基础数据(新)"""
        if(iFinD.isWin):
            if(iFinD.isless3):
                codes=c_char_p(code)
                indicator=c_char_p(Indicatorname);
                params=c_char_p(paramname);
            else:
                codes=c_char_p(bytes(code,'gbk'))
                indicator=c_char_p(bytes(Indicatorname,'gbk'));
                params=c_char_p(bytes(paramname,'gbk'));
        else:
            codes=c_char_p(bytes(code,'utf8'))
            indicator=c_char_p(bytes(Indicatorname,'utf8'));
            params=c_char_p(bytes(paramname,'utf8'));
        ptr=iFinD.c_FTQueryTHS_SynBasicDataPy(codes.value,indicator.value,params.value);
        result = cast(ptr,c_char_p).value
        data = THSData()
        indicator = Indicatorname.split(';')
        data.indicators = indicator
        data.formatResult(result,format)
        iFinD.c_DeleteMm(ptr);
        return data;

    @staticmethod
    def FTQuerySynTHS_Special_ShapePredict(code,param,begintime,endtime,outflag=False):
        import json
        """形态预测"""
        if(iFinD.isWin):
            if(iFinD.isless3):
                code=c_char_p(code)
                param=c_char_p(param);
                begintime=c_char_p(begintime);
                endtime=c_char_p(endtime);
            else:
                code=c_char_p(bytes(code,'gbk'))
                param=c_char_p(bytes(param,'gbk'));
                begintime=c_char_p(bytes(begintime,'gbk'));
                endtime=c_char_p(bytes(endtime,'gbk'));
        else:
            code=c_char_p(bytes(code,'utf8'))
            param=c_char_p(bytes(param,'utf8'));
            begintime=c_char_p(bytes(begintime,'utf8'));
            endtime=c_char_p(bytes(endtime,'utf8'));
        ptr=iFinD.c_FTQueryTHS_SynSpecial_ShapePredictPy(code.value,param.value,begintime.value,endtime.value);
        out = cast(ptr,c_char_p).value
        if outflag == False:
            out=json.loads(out.decode(iFinD.decodeMethod),object_pairs_hook=OrderedDict);
        iFinD.c_DeleteMm(ptr);
        return out;
    
    @staticmethod
    def FTQuerySynTHS_Special_StockLink(code,param,outflag=False):
        import json
        """期股联动"""
        if(iFinD.isWin):
            if(iFinD.isless3):
                code=c_char_p(code)
                param=c_char_p(param);
            else:
                code=c_char_p(bytes(code,'gbk'))
                param=c_char_p(bytes(param,'gbk'));
        else:
            code=c_char_p(bytes(code,'utf8'))
            param=c_char_p(bytes(param,'utf8'));
        ptr=iFinD.c_FTQueryTHS_SynSpecial_StockLinkPy(code.value,param.value);
        out = cast(ptr,c_char_p).value
        if outflag == False:
            out=json.loads(out.decode(iFinD.decodeMethod),object_pairs_hook=OrderedDict);
        iFinD.c_DeleteMm(ptr);
        return out;
        
    @staticmethod
    def FTQuerySynTHS_realTimeValuation(code,param,output,format='format:dataframe'):
        import json
        """基金实时估值"""
        if(iFinD.isWin):
            if(iFinD.isless3):
                code=c_char_p(code)
                param=c_char_p(param)
                output=c_char_p(output);
            else:
                code=c_char_p(bytes(code,'gbk'))
                param=c_char_p(bytes(param,'gbk'))
                output=c_char_p(bytes(output,'gbk'));
        else:
            code=c_char_p(bytes(code,'utf8'))
            param=c_char_p(bytes(param,'utf8'))
            output=c_char_p(bytes(output,'utf8'));
        ptr=iFinD.c_FTQueryTHS_SynrealTimeValuationPy(code.value,param.value,output.value);
        result = cast(ptr,c_char_p).value
        data = THSData()
        data.formatResult(result,format)
        iFinD.c_DeleteMm(ptr);
        return data;
        
    @staticmethod
    def FTQuerySynTHS_finalValuation(code,param,output,format='format:dataframe'):
        import json
        """基金实时估值(日)"""
        if(iFinD.isWin):
            if(iFinD.isless3):
                code=c_char_p(code)
                param=c_char_p(param)
                output=c_char_p(output);
            else:
                code=c_char_p(bytes(code,'gbk'))
                param=c_char_p(bytes(param,'gbk'))
                output=c_char_p(bytes(output,'gbk'));
        else:
            code=c_char_p(bytes(code,'utf8'))
            param=c_char_p(bytes(param,'utf8'))
            output=c_char_p(bytes(output,'utf8'));
        ptr=iFinD.c_FTQueryTHS_SynfinalValuationPy(code.value,param.value,output.value);
        result = cast(ptr,c_char_p).value
        data = THSData()
        data.formatResult(result,format)
        iFinD.c_DeleteMm(ptr);
        return data;
        
    @staticmethod
    def FTQuerySynTHS_ReportQuery(code,param,output,format='format:dataframe'):
        import json
        """公告查询"""
        if(iFinD.isWin):
            if(iFinD.isless3):
                code=c_char_p(code)
                param=c_char_p(param)
                output=c_char_p(output);
            else:
                code=c_char_p(bytes(code,'gbk'))
                param=c_char_p(bytes(param,'gbk'))
                output=c_char_p(bytes(output,'gbk'));
        else:
            code=c_char_p(bytes(code,'utf8'))
            param=c_char_p(bytes(param,'utf8'))
            output=c_char_p(bytes(output,'utf8'));
        ptr=iFinD.c_FTQueryTHS_SynReportQueryPy(code.value,param.value,output.value);
        result = cast(ptr,c_char_p).value
        data = THSData()
        data.formatResult(result,format)
        iFinD.c_DeleteMm(ptr);
        return data;
        
    @staticmethod
    def FTQuerySynTHS_toTHSCODE(transcontents,param,format='format:dataframe'):
        import json
        """证券代码证券简称转同花顺代码"""
        if(iFinD.isWin):
            if(iFinD.isless3):
                transcontents=c_char_p(transcontents)
                param=c_char_p(param);
            else:
                transcontents=c_char_p(bytes(transcontents,'gbk'))
                param=c_char_p(bytes(param,'gbk'));
        else:
            transcontents=c_char_p(bytes(transcontents,'utf8'))
            param=c_char_p(bytes(param,'utf8'));
        ptr=iFinD.c_FTQueryTHS_SyntoTHSCODEPy(transcontents.value,param.value);
        result = cast(ptr,c_char_p).value
        data = THSData()
        data.formatResult(result,format)
        iFinD.c_DeleteMm(ptr);
        return data;
        
    @staticmethod
    def FTQuerySynTHS_Special(type,code,param,outflag=False):
        import json
        """特色数据"""
        if(iFinD.isWin):
            if(iFinD.isless3):
                type=c_char_p(type)
                code=c_char_p(code)
                param=c_char_p(param);
            else:
                type=c_char_p(bytes(type,'gbk'))
                code=c_char_p(bytes(code,'gbk'))
                param=c_char_p(bytes(param,'gbk'));
        else:
            type=c_char_p(bytes(type,'utf8'))
            code=c_char_p(bytes(code,'utf8'))
            param=c_char_p(bytes(param,'utf8'));
        ptr=iFinD.c_FTQueryTHS_SynSpecial_Py(type.value,code.value,param.value);
        out = cast(ptr,c_char_p).value
        if outflag == False:
            out=json.loads(out.decode(iFinD.decodeMethod),object_pairs_hook=OrderedDict);
        iFinD.c_DeleteMm(ptr);
        return out;
        
    @staticmethod
    def FTQuerySyn_DataPool(DataPoolname,paramname,FunOption):
        import json
        """数据池"""
        DataPoolnames=c_wchar_p(DataPoolname);
        params=c_wchar_p(paramname);
        FunOptions=c_wchar_p(FunOption);
        out=iFinD.c_FTQuery_SynDataPoolByJsonPy(DataPoolnames.value,params.value,FunOptions.value);
        out=json.loads(out.decode(iFinD.decodeMethod,'ignore'));
        return out;

    @staticmethod
    def FTQuerySyn_HisQuote(thscode,jsonIndicator,jsonparam,begintime,endtime):
        import json
        """历史行情"""
        thscode=c_wchar_p(thscode);
        jsonIndicators=c_wchar_p(jsonIndicator);
        jsonparams=c_wchar_p(jsonparam);
        begintime=c_wchar_p(begintime);
        endtime=c_wchar_p(endtime);
        out=iFinD.c_FTQuery_SynHisQuoteByJsonPy(thscode.value,jsonIndicators.value,jsonparams.value,begintime.value,endtime.value);
        out=json.loads(out.decode(iFinD.decodeMethod));
        return out;

    @staticmethod
    def FTQueryTHS_DateSerial(thscode,jsonIndicator,jsonparam,globalparam,begintime,endtime,outflag=False):
        import json
        """日期序列"""
        if(iFinD.isWin):
            if(iFinD.isless3):
                thscode=c_char_p(thscode);
                jsonIndicators=c_char_p(jsonIndicator);
                jsonparams=c_char_p(jsonparam);
                globalparam=c_char_p(globalparam);
                begintime=c_char_p(begintime);
                endtime=c_char_p(endtime);
            else:
                thscode=c_char_p(bytes(thscode,'gbk'));
                jsonIndicators=c_char_p(bytes(jsonIndicator,'gbk'));
                jsonparams=c_char_p(bytes(jsonparam,'gbk'));
                globalparam=c_char_p(bytes(globalparam,'gbk'));
                begintime=c_char_p(bytes(begintime,'gbk'));
                endtime=c_char_p(bytes(endtime,'gbk'));
        else:
            thscode=c_char_p(bytes(thscode,'utf8'));
            jsonIndicators=c_char_p(bytes(jsonIndicator,'utf8'));
            jsonparams=c_char_p(bytes(jsonparam,'utf8'));
            globalparam=c_char_p(bytes(globalparam,'utf8'));
            begintime=c_char_p(bytes(begintime,'utf8'));
            endtime=c_char_p(bytes(endtime,'utf8'));
        ptr=iFinD.c_FTQuery_SynTHS_DateSerialPython(thscode.value,jsonIndicators.value,jsonparams.value,globalparam.value,begintime.value,endtime.value);
        out = cast(ptr,c_char_p).value
        if outflag == False:
            out = out.decode(iFinD.decodeMethod,'ignore')
            if len(out) > 0:
                out =loads_str(out)
        iFinD.c_DeleteMm(ptr);
        return out;
        
    @staticmethod
    def FTQueryTHS_DS(thscode,jsonIndicator,jsonparam,globalparam,begintime,endtime,format='format:dataframe'):
        import json
        """日期序列(新)"""
        if(iFinD.isWin):
            if(iFinD.isless3):
                thscode=c_char_p(thscode);
                jsonIndicators=c_char_p(jsonIndicator);
                jsonparams=c_char_p(jsonparam);
                globalparam=c_char_p(globalparam);
                begintime=c_char_p(begintime);
                endtime=c_char_p(endtime);
            else:
                thscode=c_char_p(bytes(thscode,'gbk'));
                jsonIndicators=c_char_p(bytes(jsonIndicator,'gbk'));
                jsonparams=c_char_p(bytes(jsonparam,'gbk'));
                globalparam=c_char_p(bytes(globalparam,'gbk'));
                begintime=c_char_p(bytes(begintime,'gbk'));
                endtime=c_char_p(bytes(endtime,'gbk'));
        else:
            thscode=c_char_p(bytes(thscode,'utf8'));
            jsonIndicators=c_char_p(bytes(jsonIndicator,'utf8'));
            jsonparams=c_char_p(bytes(jsonparam,'utf8'));
            globalparam=c_char_p(bytes(globalparam,'utf8'));
            begintime=c_char_p(bytes(begintime,'utf8'));
            endtime=c_char_p(bytes(endtime,'utf8'));
        ptr=iFinD.c_FTQuery_SynTHS_DateSerialPython(thscode.value,jsonIndicators.value,jsonparams.value,globalparam.value,begintime.value,endtime.value);
        result = cast(ptr,c_char_p).value
        data = THSData()
        indicator = jsonIndicator.split(';')
        data.indicators = indicator
        data.formatResult(result,format)
        iFinD.c_DeleteMm(ptr);
        return data;

    @staticmethod
    def FTQuerySynTHS_Snapshot(thscode,jsonIndicator,jsonparam,begintime,endtime,outflag=False):
        import json
        """快照数据"""
        if(iFinD.isWin):
            if(iFinD.isless3):
                thscode=c_char_p(thscode);
                jsonIndicators=c_char_p(jsonIndicator);
                jsonparams=c_char_p(jsonparam);
                begintime=c_char_p(begintime);
                endtime=c_char_p(endtime);
            else:
                thscode=c_char_p(bytes(thscode,'gbk'));
                jsonIndicators=c_char_p(bytes(jsonIndicator,'gbk'));
                jsonparams=c_char_p(bytes(jsonparam,'gbk'));
                begintime=c_char_p(bytes(begintime,'gbk'));
                endtime=c_char_p(bytes(endtime,'gbk'));
        else:
            thscode=c_char_p(bytes(thscode,'utf8'));
            jsonIndicators=c_char_p(bytes(jsonIndicator,'utf8'));
            jsonparams=c_char_p(bytes(jsonparam,'utf8'));
            begintime=c_char_p(bytes(begintime,'utf8'));
            endtime=c_char_p(bytes(endtime,'utf8'));
        ptr=iFinD.c_FTQuery_SynSnapshotPy(thscode.value,jsonIndicators.value,jsonparams.value,begintime.value,endtime.value);
        out = cast(ptr,c_char_p).value
        if outflag == False:
            out=json.loads(out.decode(iFinD.decodeMethod),object_pairs_hook=OrderedDict);
        iFinD.c_DeleteMm(ptr);
        return out;
        
    @staticmethod
    def FTQuerySynTHS_SS(thscode,jsonIndicator,jsonparam,begintime,endtime,format='format:dataframe'):
        """快照数据(新)"""
        if(iFinD.isWin):
            if(iFinD.isless3):
                thscode=c_char_p(thscode);
                jsonIndicators=c_char_p(jsonIndicator);
                jsonparams=c_char_p(jsonparam);
                begintime=c_char_p(begintime);
                endtime=c_char_p(endtime);
            else:
                thscode=c_char_p(bytes(thscode,'gbk'));
                jsonIndicators=c_char_p(bytes(jsonIndicator,'gbk'));
                jsonparams=c_char_p(bytes(jsonparam,'gbk'));
                begintime=c_char_p(bytes(begintime,'gbk'));
                endtime=c_char_p(bytes(endtime,'gbk'));
        else:
            thscode=c_char_p(bytes(thscode,'utf8'));
            jsonIndicators=c_char_p(bytes(jsonIndicator,'utf8'));
            jsonparams=c_char_p(bytes(jsonparam,'utf8'));
            begintime=c_char_p(bytes(begintime,'utf8'));
            endtime=c_char_p(bytes(endtime,'utf8'));
        ptr=iFinD.c_FTQuery_SynSnapshotPy(thscode.value,jsonIndicators.value,jsonparams.value,begintime.value,endtime.value);
        result = cast(ptr,c_char_p).value
        data = THSData()
        indicator = jsonIndicator.split(';')
        data.indicators = indicator
        data.formatResult(result,format)
        iFinD.c_DeleteMm(ptr);
        return data;

    @staticmethod
    def FTQuerySynTHS_DataPool(DataPoolname,paramname,FunOption,outflag=False):
        import json
        """数据池"""
        if(iFinD.isWin):
            if(iFinD.isless3):
                DataPoolnames=c_char_p(DataPoolname);
                params=c_char_p(paramname);
                FunOptions=c_char_p(FunOption);
            else:
                DataPoolnames=c_char_p(bytes(DataPoolname,'gbk'));
                params=c_char_p(bytes(paramname,'gbk'));
                FunOptions=c_char_p(bytes(FunOption,'gbk'));
        else:
            DataPoolnames=c_char_p(bytes(DataPoolname,'utf8'));
            params=c_char_p(bytes(paramname,'utf8'));
            FunOptions=c_char_p(bytes(FunOption,'utf8'));
        ptr=iFinD.c_FTQueryTHS_SynDataPoolByJsonPy(DataPoolnames.value,params.value,FunOptions.value);
        out = cast(ptr,c_char_p).value
        if outflag == False:
            out = out.decode(iFinD.decodeMethod,'ignore')
            if len(out) > 0:
                out =loads_str(out)
        iFinD.c_DeleteMm(ptr);
        return out;
        
    @staticmethod
    def FTQuerySynTHS_DP(DataPoolname,paramname,FunOption,format='format:dataframe'):
        """数据池(新)"""
        if(iFinD.isWin):
            if(iFinD.isless3):
                DataPoolnames=c_char_p(DataPoolname);
                params=c_char_p(paramname);
                FunOptions=c_char_p(FunOption);
            else:
                DataPoolnames=c_char_p(bytes(DataPoolname,'gbk'));
                params=c_char_p(bytes(paramname,'gbk'));
                FunOptions=c_char_p(bytes(FunOption,'gbk'));
        else:
            DataPoolnames=c_char_p(bytes(DataPoolname,'utf8'));
            params=c_char_p(bytes(paramname,'utf8'));
            FunOptions=c_char_p(bytes(FunOption,'utf8'));
        ptr=iFinD.c_FTQueryTHS_SynDataPoolByJsonPy(DataPoolnames.value,params.value,FunOptions.value);
        result = cast(ptr,c_char_p).value
        data = THSData()
        #indicator = FunOption.split(',')
        #data.indicators = indicator
        data.formatResult(result,format)
        if ('block' == DataPoolname) or ('index' == DataPoolname):
            obj = json.loads(result.decode(iFinD.decodeMethod,'ignore'))
            tables = obj.get('tables')
            if (tables is not None) and len(tables) > 0:
                table = tables[0].get('table')
                if (table is not None):
                    data.thscode = table.get('THSCODE',[])
        iFinD.c_DeleteMm(ptr);
        return data;
        
    @staticmethod
    def FTQuerySynTHS_iResearch(name,paramname,FunOption,format='format:dataframe'):
        """AI预测"""
        if(iFinD.isWin):
            if(iFinD.isless3):
                name=c_char_p(name);
                params=c_char_p(paramname);
                FunOptions=c_char_p(FunOption);
            else:
                name=c_char_p(bytes(name,'gbk'));
                params=c_char_p(bytes(paramname,'gbk'));
                FunOptions=c_char_p(bytes(FunOption,'gbk'));
        else:
            name=c_char_p(bytes(name,'utf8'));
            params=c_char_p(bytes(paramname,'utf8'));
            FunOptions=c_char_p(bytes(FunOption,'utf8'));
        ptr=iFinD.c_FTQueryTHS_SyniResearchByJsonPy(name.value,params.value,FunOptions.value);
        result = cast(ptr,c_char_p).value
        data = THSData()
        data.formatResult(result,format)
        iFinD.c_DeleteMm(ptr);
        return data;
        
    @staticmethod
    def FTQuerySynTHS_iEvent(name,paramname,FunOption,format='format:dataframe'):
        """事件驱动"""
        if(iFinD.isWin):
            if(iFinD.isless3):
                name=c_char_p(name);
                params=c_char_p(paramname);
                FunOptions=c_char_p(FunOption);
            else:
                name=c_char_p(bytes(name,'gbk'));
                params=c_char_p(bytes(paramname,'gbk'));
                FunOptions=c_char_p(bytes(FunOption,'gbk'));
        else:
            name=c_char_p(bytes(name,'utf8'));
            params=c_char_p(bytes(paramname,'utf8'));
            FunOptions=c_char_p(bytes(FunOption,'utf8'));
        ptr=iFinD.c_FTQueryTHS_SyniEventByJsonPy(name.value,params.value,FunOptions.value);
        result = cast(ptr,c_char_p).value
        data = THSData()
        data.formatResult(result,format)
        iFinD.c_DeleteMm(ptr);
        return data;
        
    @staticmethod
    def FTQuerySynTHS_iTranslate(name,paramname,FunOption,format='format:json'):
        """AI翻译"""
        if(iFinD.isWin):
            if(iFinD.isless3):
                name=c_char_p(name);
                params=c_char_p(paramname);
                FunOptions=c_char_p(FunOption);
            else:
                name=c_char_p(bytes(name,'gbk'));
                params=c_char_p(bytes(paramname,'gbk'));
                FunOptions=c_char_p(bytes(FunOption,'gbk'));
        else:
            name=c_char_p(bytes(name,'utf8'));
            params=c_char_p(bytes(paramname,'utf8'));
            FunOptions=c_char_p(bytes(FunOption,'utf8'));
        ptr=iFinD.c_FTQueryTHS_SyniTranslateByJsonPy(name.value,params.value,FunOptions.value);
        result = cast(ptr,c_char_p).value
        data = THSData()
        data.formatResult(result,format)
        data.data=result
        iFinD.c_DeleteMm(ptr);
        return data;
        
    @staticmethod
    def FTQuerySynTHS_DR(TPname,paramname,FunOption,format='format:dataframe'):
        """专题报表"""
        if(iFinD.isWin):
            if(iFinD.isless3):
                TPnames=c_char_p(TPname);
                params=c_char_p(paramname);
                FunOptions=c_char_p(FunOption);
            else:
                TPnames=c_char_p(bytes(TPname,'gbk'));
                params=c_char_p(bytes(paramname,'gbk'));
                FunOptions=c_char_p(bytes(FunOption,'gbk'));
        else:
            TPnames=c_char_p(bytes(DataPoolname,'utf8'));
            params=c_char_p(bytes(paramname,'utf8'));
            FunOptions=c_char_p(bytes(FunOption,'utf8'));
        ptr=iFinD.c_FTQueryTHS_SynDRByJsonPy(TPnames.value,params.value,FunOptions.value);
        result = cast(ptr,c_char_p).value
        data = THSData()
        data.formatResult(result,format)
        iFinD.c_DeleteMm(ptr);
        return data;
        
    @staticmethod
    def FTQuerySynTHS_RPT(TPname,version,paramname,FunOption,format='format:dataframe'):
        """专题报表(新)"""
        if(iFinD.isWin):
            if(iFinD.isless3):
                TPnames=c_char_p(TPname);
                version=c_char_p(version);
                params=c_char_p(paramname);
                FunOptions=c_char_p(FunOption);
            else:
                TPnames=c_char_p(bytes(TPname,'gbk'));
                version=c_char_p(bytes(version,'gbk'));
                params=c_char_p(bytes(paramname,'gbk'));
                FunOptions=c_char_p(bytes(FunOption,'gbk'));
        else:
            TPnames=c_char_p(bytes(DataPoolname,'utf8'));
            version=c_char_p(bytes(version,'utf8'));
            params=c_char_p(bytes(paramname,'utf8'));
            FunOptions=c_char_p(bytes(FunOption,'utf8'));
        ptr=iFinD.c_FTQueryTHS_SynRPTByJsonPy(TPnames.value,version.value,params.value,FunOptions.value);
        result = cast(ptr,c_char_p).value
        data = THSData()
        data.formatResult(result,format)
        iFinD.c_DeleteMm(ptr);
        return data;
        
    @staticmethod
    def FTQuerySynTHS_FEB(params,FunOption,format='format:dataframe'):
        """财经早餐"""
        if(iFinD.isWin):
            if(iFinD.isless3):
                params=c_char_p(params);
                FunOptions=c_char_p(FunOption);
            else:
                params=c_char_p(bytes(params,'gbk'));
                FunOptions=c_char_p(bytes(FunOption,'gbk'));
        else:
            params=c_char_p(bytes(params,'utf8'));
            FunOptions=c_char_p(bytes(FunOption,'utf8'));
        ptr=iFinD.c_FTQueryTHS_SynFEBByJsonPy(params.value,FunOptions.value);
        result = cast(ptr,c_char_p).value
        data = THSData()
        data.formatResult(result,format)
        iFinD.c_DeleteMm(ptr);
        return data;

    @staticmethod
    def FTQuerySynTHS_HQ(thscode,jsonIndicator,jsonparam,begintime,endtime,format='format:dataframe'):
        """历史行情(新)"""
        if(iFinD.isWin):
            if(iFinD.isless3):
                thscode=c_char_p(thscode);
                jsonIndicators=c_char_p(jsonIndicator);
                jsonparams=c_char_p(jsonparam);
                begintime=c_char_p(begintime);
                endtime=c_char_p(endtime);
            else:
                thscode=c_char_p(bytes(thscode,'gbk'));
                jsonIndicators=c_char_p(bytes(jsonIndicator,'gbk'));
                jsonparams=c_char_p(bytes(jsonparam,'gbk'));
                begintime=c_char_p(bytes(begintime,'gbk'));
                endtime=c_char_p(bytes(endtime,'gbk'));
        else:
            thscode=c_char_p(bytes(thscode,'utf8'));
            jsonIndicators=c_char_p(bytes(jsonIndicator,'utf8'));
            jsonparams=c_char_p(bytes(jsonparam,'utf8'));
            begintime=c_char_p(bytes(begintime,'utf8'));
            endtime=c_char_p(bytes(endtime,'utf8'));        
        ptr=iFinD.c_FTQueryTHS_SynHisQuoteByJsonPy(thscode.value,jsonIndicators.value,jsonparams.value,begintime.value,endtime.value);
        result = cast(ptr,c_char_p).value
        data = THSData()
        indicator = jsonIndicator.split(',')
        data.indicators = indicator
        data.formatResult(result,format)
        iFinD.c_DeleteMm(ptr);
        return data;

    @staticmethod
    def FTQuerySynTHS_HD(thscode,jsonIndicator,jsonparam,begintime,endtime,format='format:dataframe'):
        """历史行情(新1)"""
        if(iFinD.isWin):
            if(iFinD.isless3):
                thscode=c_char_p(thscode);
                jsonIndicators=c_char_p(jsonIndicator);
                jsonparams=c_char_p(jsonparam);
                begintime=c_char_p(begintime);
                endtime=c_char_p(endtime);
            else:
                thscode=c_char_p(bytes(thscode,'gbk'));
                jsonIndicators=c_char_p(bytes(jsonIndicator,'gbk'));
                jsonparams=c_char_p(bytes(jsonparam,'gbk'));
                begintime=c_char_p(bytes(begintime,'gbk'));
                endtime=c_char_p(bytes(endtime,'gbk'));
        else:
            thscode=c_char_p(bytes(thscode,'utf8'));
            jsonIndicators=c_char_p(bytes(jsonIndicator,'utf8'));
            jsonparams=c_char_p(bytes(jsonparam,'utf8'));
            begintime=c_char_p(bytes(begintime,'utf8'));
            endtime=c_char_p(bytes(endtime,'utf8'));        
        ptr=iFinD.c_FTQueryTHS_SynHDByJsonPy(thscode.value,jsonIndicators.value,jsonparams.value,begintime.value,endtime.value);
        result = cast(ptr,c_char_p).value
        data = THSData()
        indicator = jsonIndicator.split(',')
        data.indicators = indicator
        data.formatResult(result,format)
        iFinD.c_DeleteMm(ptr);
        return data;
        
    @staticmethod
    def FTQuerySynTHS_HisQuote(thscode,jsonIndicator,jsonparam,begintime,endtime,outflag=False):
        import json
        """历史行情"""
        if(iFinD.isWin):
            if(iFinD.isless3):
                thscode=c_char_p(thscode);
                jsonIndicators=c_char_p(jsonIndicator);
                jsonparams=c_char_p(jsonparam);
                begintime=c_char_p(begintime);
                endtime=c_char_p(endtime);
            else:
                thscode=c_char_p(bytes(thscode,'gbk'));
                jsonIndicators=c_char_p(bytes(jsonIndicator,'gbk'));
                jsonparams=c_char_p(bytes(jsonparam,'gbk'));
                begintime=c_char_p(bytes(begintime,'gbk'));
                endtime=c_char_p(bytes(endtime,'gbk'));
        else:
            thscode=c_char_p(bytes(thscode,'utf8'));
            jsonIndicators=c_char_p(bytes(jsonIndicator,'utf8'));
            jsonparams=c_char_p(bytes(jsonparam,'utf8'));
            begintime=c_char_p(bytes(begintime,'utf8'));
            endtime=c_char_p(bytes(endtime,'utf8'));        
        ptr=iFinD.c_FTQueryTHS_SynHisQuoteByJsonPy(thscode.value,jsonIndicators.value,jsonparams.value,begintime.value,endtime.value);
        out = cast(ptr,c_char_p).value
        if outflag == False:
            out=json.loads(out.decode(iFinD.decodeMethod),object_pairs_hook=OrderedDict);
        iFinD.c_DeleteMm(ptr);
        return out;

    @staticmethod
    def FT_EDBQuery(indicators, begintime, endtime, outflag=False):
        """查询EDB"""
        import json
        if(iFinD.isWin):
            if(iFinD.isless3):
                Indicators=c_char_p(indicators);
                Begintime=c_char_p(begintime);
                Endtime=c_char_p(endtime);
            else:
                Indicators=c_char_p(bytes(indicators,'gbk'));
                Begintime=c_char_p(bytes(begintime,'gbk'));
                Endtime=c_char_p(bytes(endtime,'gbk'));
        else:
            Indicators=c_char_p(bytes(indicators,'utf8'));
            Begintime=c_char_p(bytes(begintime,'utf8'));
            Endtime=c_char_p(bytes(endtime,'utf8'));
        ptr=iFinD.C_FT_ifinDEDBQuery(Indicators.value, Begintime.value, Endtime.value);
        out = cast(ptr,c_char_p).value
        if outflag == False:
            out = out.decode(iFinD.decodeMethod,'ignore')
            if len(out) > 0:
                out =loads_str(out)
        iFinD.c_DeleteMm(ptr);
        return out;
        
    @staticmethod
    def FT_EDB(indicators, param, begintime, endtime, format='format:dataframe'):
        """查询EDB"""
        import json
        if(iFinD.isWin):
            if(iFinD.isless3):
                Indicators=c_char_p(indicators);
                Param = c_char_p(param);
                Begintime=c_char_p(begintime);
                Endtime=c_char_p(endtime);
            else:
                Indicators=c_char_p(bytes(indicators,'gbk'));
                Param=c_char_p(bytes(param,'gbk'));
                Begintime=c_char_p(bytes(begintime,'gbk'));
                Endtime=c_char_p(bytes(endtime,'gbk'));
        else:
            Indicators=c_char_p(bytes(indicators,'utf8'));
            Param=c_char_p(bytes(param,'gbk'));
            Begintime=c_char_p(bytes(begintime,'utf8'));
            Endtime=c_char_p(bytes(endtime,'utf8'));
        ptr=iFinD.C_FT_ifinDEDB(Indicators.value, Param.value, Begintime.value, Endtime.value);
        result = cast(ptr,c_char_p).value
        data = THSData()
        thscode = indicators.split(';')
        data.thscode = thscode
        data.formatResult(result,format)
        iFinD.c_DeleteMm(ptr);
        return data;

    @staticmethod
    def FT_iwencai(query,domain,outflag=False):
        import json
        if(iFinD.isWin):
            if(iFinD.isless3):
                first=c_char_p(query);
                second=c_char_p(domain);
            else:
                first=c_char_p(bytes(query,'gbk'));
                second=c_char_p(bytes(domain,'gbk'));
        else:
             first=c_char_p(bytes(query,'utf8'));
             second=c_char_p(bytes(domain,'utf8'));
        ptr=iFinD.C_FT_ifinDiwencai(first.value,second.value);
        out=cast(ptr,c_char_p).value
        if outflag == False:
            out = out.decode(iFinD.decodeMethod,'ignore')
            if len(out) > 0:
                out =loads_str(out)
        iFinD.c_DeleteMm(ptr);
        return out;   
        
    @staticmethod
    def FT_WCQuery(query,domain,format='format:dataframe'):
        import json
        if(iFinD.isWin):
            if(iFinD.isless3):
                first=c_char_p(query);
                second=c_char_p(domain);
            else:
                first=c_char_p(bytes(query,'gbk'));
                second=c_char_p(bytes(domain,'gbk'));
        else:
             first=c_char_p(bytes(query,'utf8'));
             second=c_char_p(bytes(domain,'utf8'));
        ptr=iFinD.C_FT_ifinDWCQuery(first.value,second.value);
        result = cast(ptr,c_char_p).value
        data = THSData()
        data.formatResult(result,format)
        iFinD.c_DeleteMm(ptr);
        return data;
        
    @staticmethod
    def FT_WC(query,domain,format='format:dataframe'):
        if(iFinD.isWin):
            if(iFinD.isless3):
                first=c_char_p(query);
                second=c_char_p(domain);
            else:
                first=c_char_p(bytes(query,'gbk'));
                second=c_char_p(bytes(domain,'gbk'));
        else:
             first=c_char_p(bytes(query,'utf8'));
             second=c_char_p(bytes(domain,'utf8'));
        ptr=iFinD.C_FT_ifinDiwencai(first.value,second.value);
        result = cast(ptr,c_char_p).value
        data = THSData()
        data.formatResult(result,format)
        iFinD.c_DeleteMm(ptr);
        return data;

    @staticmethod
    def FTQueryTHS_BasicData(thsCode, indicatorName, paramOption,CBResultsFunc,pUser,piQueryID):
        if(iFinD.isWin):
            if(iFinD.isless3):
                thsCode=c_char_p(thsCode);
                indicatorName=c_char_p(indicatorName);
                paramOption=c_char_p(paramOption);
            else:
                thsCode=c_char_p(bytes(thsCode,'gbk'));
                indicatorName=c_char_p(bytes(indicatorName,'gbk'));
                paramOption=c_char_p(bytes(paramOption,'gbk'));
        else:
            thsCode=c_char_p(bytes(thsCode,'utf8'));
            indicatorName=c_char_p(bytes(indicatorName,'utf8'));
            paramOption=c_char_p(bytes(paramOption,'utf8'));
        pIQueryID=c_int(0);
        out=iFinD.c_FTQueryTHS_BasicDataPy(thsCode.value,indicatorName.value,paramOption.value,pAsyFunc,pUser,byref(pIQueryID)) 
        iFinD.c_SetValue(pIQueryID,piQueryID)
        if(out==0):
            global g_FunctionMgr
            global g_Funclock
            g_Funclock.acquire();
            g_FunctionMgr[pIQueryID.value] = CBResultsFunc
            g_Funclock.release()
        return out;

    @staticmethod
    def FTQueryTHS_DataPool(DataPool,indicatorName,ParamOption,CBResultsFunc,pUser,piQueryID):
        if(iFinD.isWin):
            if(iFinD.isless3):
                DataPool=c_char_p(DataPool);
                indicatorName=c_char_p(indicatorName);
                ParamOption=c_char_p(ParamOption);
            else:
                DataPool=c_char_p(bytes(DataPool,'gbk'));
                indicatorName=c_char_p(bytes(indicatorName,'gbk'));
                ParamOption=c_char_p(bytes(ParamOption,'gbk')); 
        else:
            DataPool=c_char_p(bytes(DataPool,'utf8'));
            indicatorName=c_char_p(bytes(indicatorName,'utf8'));
            ParamOption=c_char_p(bytes(ParamOption,'utf8'));   
        pIQueryID=c_int(0);
        out=iFinD.c_FTQueryTHS_DatapoolPy(DataPool.value,indicatorName.value,ParamOption.value,pAsyFunc,pUser,byref(pIQueryID));
        iFinD.c_SetValue(pIQueryID,piQueryID)
        if(out==0):
            global g_FunctionMgr
            global g_Funclock
            g_Funclock.acquire();
            g_FunctionMgr[pIQueryID.value] = CBResultsFunc
            g_Funclock.release()
        return out;
        
    @staticmethod
    def FTQueryTHS_DR(TPname,indicatorName,ParamOption,CBResultsFunc,pUser,piQueryID):
        if(iFinD.isWin):
            if(iFinD.isless3):
                TPname=c_char_p(TPname);
                indicatorName=c_char_p(indicatorName);
                ParamOption=c_char_p(ParamOption);
            else:
                TPname=c_char_p(bytes(TPname,'gbk'));
                indicatorName=c_char_p(bytes(indicatorName,'gbk'));
                ParamOption=c_char_p(bytes(ParamOption,'gbk')); 
        else:
            TPname=c_char_p(bytes(TPname,'utf8'));
            indicatorName=c_char_p(bytes(indicatorName,'utf8'));
            ParamOption=c_char_p(bytes(ParamOption,'utf8'));   
        pIQueryID=c_int(0);
        out=iFinD.c_FTQueryTHS_DRPy(TPname.value,indicatorName.value,ParamOption.value,pAsyFunc,pUser,byref(pIQueryID));
        iFinD.c_SetValue(pIQueryID,piQueryID)
        if(out==0):
            global g_FunctionMgr
            global g_Funclock
            g_Funclock.acquire();
            g_FunctionMgr[pIQueryID.value] = CBResultsFunc
            g_Funclock.release()
        return out;
        
    @staticmethod
    def FTQueryTHS_RPT(TPname,version,indicatorName,ParamOption,CBResultsFunc,pUser,piQueryID):
        if(iFinD.isWin):
            if(iFinD.isless3):
                TPname=c_char_p(TPname);
                version=c_char_p(version);
                indicatorName=c_char_p(indicatorName);
                ParamOption=c_char_p(ParamOption);
            else:
                TPname=c_char_p(bytes(TPname,'gbk'));
                version=c_char_p(bytes(version,'gbk'));
                indicatorName=c_char_p(bytes(indicatorName,'gbk'));
                ParamOption=c_char_p(bytes(ParamOption,'gbk')); 
        else:
            TPname=c_char_p(bytes(TPname,'utf8'));
            version=c_char_p(bytes(version,'utf8'));
            indicatorName=c_char_p(bytes(indicatorName,'utf8'));
            ParamOption=c_char_p(bytes(ParamOption,'utf8'));   
        pIQueryID=c_int(0);
        out=iFinD.c_FTQueryTHS_RPTPy(TPname.value,version.value,indicatorName.value,ParamOption.value,pAsyFunc,pUser,byref(pIQueryID));
        iFinD.c_SetValue(pIQueryID,piQueryID)
        if(out==0):
            global g_FunctionMgr
            global g_Funclock
            g_Funclock.acquire();
            g_FunctionMgr[pIQueryID.value] = CBResultsFunc
            g_Funclock.release()
        return out;
        
    @staticmethod
    def FTQueryTHS_iResearch(name,indicatorName,ParamOption,CBResultsFunc,pUser,piQueryID):
        if(iFinD.isWin):
            if(iFinD.isless3):
                name=c_char_p(name);
                indicatorName=c_char_p(indicatorName);
                ParamOption=c_char_p(ParamOption);
            else:
                name=c_char_p(bytes(name,'gbk'));
                indicatorName=c_char_p(bytes(indicatorName,'gbk'));
                ParamOption=c_char_p(bytes(ParamOption,'gbk')); 
        else:
            name=c_char_p(bytes(name,'utf8'));
            indicatorName=c_char_p(bytes(indicatorName,'utf8'));
            ParamOption=c_char_p(bytes(ParamOption,'utf8'));   
        pIQueryID=c_int(0);
        out=iFinD.c_FTQueryTHS_iResearchPy(name.value,indicatorName.value,ParamOption.value,pAsyFunc,pUser,byref(pIQueryID));
        iFinD.c_SetValue(pIQueryID,piQueryID)
        if(out==0):
            global g_FunctionMgr
            global g_Funclock
            g_Funclock.acquire();
            g_FunctionMgr[pIQueryID.value] = CBResultsFunc
            g_Funclock.release()
        return out;
        
    @staticmethod
    def FTQueryTHS_iEvent(name,indicatorName,ParamOption,CBResultsFunc,pUser,piQueryID):
        if(iFinD.isWin):
            if(iFinD.isless3):
                name=c_char_p(name);
                indicatorName=c_char_p(indicatorName);
                ParamOption=c_char_p(ParamOption);
            else:
                name=c_char_p(bytes(name,'gbk'));
                indicatorName=c_char_p(bytes(indicatorName,'gbk'));
                ParamOption=c_char_p(bytes(ParamOption,'gbk')); 
        else:
            name=c_char_p(bytes(name,'utf8'));
            indicatorName=c_char_p(bytes(indicatorName,'utf8'));
            ParamOption=c_char_p(bytes(ParamOption,'utf8'));   
        pIQueryID=c_int(0);
        out=iFinD.c_FTQueryTHS_iEventPy(name.value,indicatorName.value,ParamOption.value,pAsyFunc,pUser,byref(pIQueryID));
        iFinD.c_SetValue(pIQueryID,piQueryID)
        if(out==0):
            global g_FunctionMgr
            global g_Funclock
            g_Funclock.acquire();
            g_FunctionMgr[pIQueryID.value] = CBResultsFunc
            g_Funclock.release()
        return out;
        
    @staticmethod
    def FTQueryTHS_iTranslate(name,indicatorName,ParamOption,CBResultsFunc,pUser,piQueryID):
        if(iFinD.isWin):
            if(iFinD.isless3):
                name=c_char_p(name);
                indicatorName=c_char_p(indicatorName);
                ParamOption=c_char_p(ParamOption);
            else:
                name=c_char_p(bytes(name,'gbk'));
                indicatorName=c_char_p(bytes(indicatorName,'gbk'));
                ParamOption=c_char_p(bytes(ParamOption,'gbk')); 
        else:
            name=c_char_p(bytes(name,'utf8'));
            indicatorName=c_char_p(bytes(indicatorName,'utf8'));
            ParamOption=c_char_p(bytes(ParamOption,'utf8'));   
        pIQueryID=c_int(0);
        out=iFinD.c_FTQueryTHS_iTranslatePy(name.value,indicatorName.value,ParamOption.value,pAsyFunc,pUser,byref(pIQueryID));
        iFinD.c_SetValue(pIQueryID,piQueryID)
        if(out==0):
            global g_FunctionMgr
            global g_Funclock
            g_Funclock.acquire();
            g_FunctionMgr[pIQueryID.value] = CBResultsFunc
            g_Funclock.release()
        return out;

    @staticmethod
    def FTQueryTHS_DateSequence(thscode,jsonIndicator,jsonparam,begintime,endtime,CBResultsFunc,pUser,piQueryID):
        if(iFinD.isWin):
            if(iFinD.isless3):
                thscode=c_char_p(thscode);
                jsonIndicators=c_char_p(jsonIndicator);
                jsonparams=c_char_p(jsonparam);
                begintime=c_char_p(begintime);
                endtime=c_char_p(endtime);
            else:
                thscode=c_char_p(bytes(thscode,'gbk'));
                jsonIndicators=c_char_p(bytes(jsonIndicator,'gbk'));
                jsonparams=c_char_p(bytes(jsonparam,'gbk'));
                begintime=c_char_p(bytes(begintime,'gbk'));
                endtime=c_char_p(bytes(endtime,'gbk')); 
        else:
            thscode=c_char_p(bytes(thscode,'utf8'));
            jsonIndicators=c_char_p(bytes(jsonIndicator,'utf8'));
            jsonparams=c_char_p(bytes(jsonparam,'utf8'));
            begintime=c_char_p(bytes(begintime,'utf8'));
            endtime=c_char_p(bytes(endtime,'utf8'));    
        pIQueryID=c_int(0);
        out=iFinD.c_FTQueryTHS_DateSequencePy(thscode.value,jsonIndicators.value,jsonparams.value,begintime.value,endtime.value,pAsyFunc,pUser,byref(pIQueryID))
        iFinD.c_SetValue(pIQueryID,piQueryID)
        if(out==0):
            global g_FunctionMgr
            global g_Funclock
            g_Funclock.acquire();
            g_FunctionMgr[pIQueryID.value] = CBResultsFunc
            g_Funclock.release()
        return out;

    @staticmethod
    def FTQueryTHS_RealtimeQuotes(thscode,jsonIndicator,jsonparam,CBResultsFunc,pUser,piQueryID):
        if(iFinD.isWin):
            if(iFinD.isless3):
                thscode=c_char_p(thscode);
                jsonIndicators=c_char_p(jsonIndicator);
                jsonparams=c_char_p(jsonparam);
            else:
                thscode=c_char_p(bytes(thscode,'gbk'));
                jsonIndicators=c_char_p(bytes(jsonIndicator,'gbk'));
                jsonparams=c_char_p(bytes(jsonparam,'gbk'));
        else:
            thscode=c_char_p(bytes(thscode,'utf8'));
            jsonIndicators=c_char_p(bytes(jsonIndicator,'utf8'));
            jsonparams=c_char_p(bytes(jsonparam,'utf8'));      
        onlyonce=c_bool(True);
        pIQueryID=c_int(0);
        out=iFinD.c_FTQueryTHS_RealtimeQuotesPy(thscode.value,jsonIndicators.value,jsonparams.value,onlyonce,pAsyFunc,pUser,byref(pIQueryID))
        iFinD.c_SetValue(pIQueryID,piQueryID)
        if(out==0):
            global g_FunctionMgr
            global g_Funclock
            g_Funclock.acquire();
            g_FunctionMgr[pIQueryID.value] = CBResultsFunc
            g_Funclock.release()
        return out;

    @staticmethod
    def FTQueryTHS_HighFrequenceSequence(thscode,jsonIndicator,jsonparam,begintime,endtime,CBResultsFunc,pUser,piQueryID):
        if(iFinD.isWin):
            if(iFinD.isless3):
                thscode=c_char_p(thscode);
                jsonIndicators=c_char_p(jsonIndicator);
                jsonparams=c_char_p(jsonparam);
                begintime=c_char_p(begintime);
                endtime=c_char_p(endtime);
            else:
                thscode=c_char_p(bytes(thscode,'gbk'));
                jsonIndicators=c_char_p(bytes(jsonIndicator,'gbk'));
                jsonparams=c_char_p(bytes(jsonparam,'gbk'));
                begintime=c_char_p(bytes(begintime,'gbk'));
                endtime=c_char_p(bytes(endtime,'gbk'));
        else:
            thscode=c_char_p(bytes(thscode,'utf8'));
            jsonIndicators=c_char_p(bytes(jsonIndicator,'utf8'));
            jsonparams=c_char_p(bytes(jsonparam,'utf8'));
            begintime=c_char_p(bytes(begintime,'utf8'));
            endtime=c_char_p(bytes(endtime,'utf8'));      
        pIQueryID=c_int(0);
        #CBResultsFunc=CMPTHSREALTIMEFUNC(CBResultsFunc);
        #out=iFinD.c_FTQueryTHS_HighFrequenceSequencePy(thscode.value,jsonIndicators.value,jsonparams.value,begintime.value,endtime.value,CBResultsFunc,c_void_p(pUser),byref(piQueryID))
        out=iFinD.c_FTQueryTHS_HighFrequenceSequencePy(thscode.value,jsonIndicators.value,jsonparams.value,begintime.value,endtime.value,pAsyFunc,pUser,byref(pIQueryID))
        iFinD.c_SetValue(pIQueryID,piQueryID)
        if(out==0):
            global g_FunctionMgr
            global g_FunctionMgr
            global g_Funclock
            g_Funclock.acquire();
            g_FunctionMgr[pIQueryID.value] = CBResultsFunc
            g_Funclock.release()
        return out;

    @staticmethod
    def FTQueryTHS_HisQuote(thscode,jsonIndicator,jsonparam,begintime,endtime,CBResultsFunc,pUser,piQueryID):
        if(iFinD.isWin):
            if(iFinD.isless3):
                thscode=c_char_p(thscode);
                jsonIndicators=c_char_p(jsonIndicator);
                jsonparams=c_char_p(jsonparam);
                begintime=c_char_p(begintime);
                endtime=c_char_p(endtime);
            else:
                thscode=c_char_p(bytes(thscode,'gbk'));
                jsonIndicators=c_char_p(bytes(jsonIndicator,'gbk'));
                jsonparams=c_char_p(bytes(jsonparam,'gbk'));
                begintime=c_char_p(bytes(begintime,'gbk'));
                endtime=c_char_p(bytes(endtime,'gbk')); 
        else:
            thscode=c_char_p(bytes(thscode,'utf8'));
            jsonIndicators=c_char_p(bytes(jsonIndicator,'utf8'));
            jsonparams=c_char_p(bytes(jsonparam,'utf8'));
            begintime=c_char_p(bytes(begintime,'utf8'));
            endtime=c_char_p(bytes(endtime,'utf8'));     
        pIQueryID=c_int(0);
        out=iFinD.c_FTQueryTHS_HisQuotePy(thscode.value,jsonIndicators.value,jsonparams.value,begintime.value,endtime.value,pAsyFunc,pUser,byref(pIQueryID))
        iFinD.c_SetValue(pIQueryID,piQueryID)
        if(out==0):
            global g_FunctionMgr
            global g_Funclock
            g_Funclock.acquire();
            g_FunctionMgr[pIQueryID.value] = CBResultsFunc
            g_Funclock.release()
        return out;

    @staticmethod
    def FTQueryTHS_AsyDateSerial(thscode,jsonIndicator,jsonparam,globalparam,begintime,endtime,CBResultsFunc,pUser,piQueryID):
        if(iFinD.isWin):
            if(iFinD.isless3):
                thscode=c_char_p(thscode);
                jsonIndicators=c_char_p(jsonIndicator);
                globalp=c_char_p(globalparam);
                jsonparams=c_char_p(jsonparam);
                begintime=c_char_p(begintime);
                endtime=c_char_p(endtime);
            else:
                thscode=c_char_p(bytes(thscode,'gbk'));
                jsonIndicators=c_char_p(bytes(jsonIndicator,'gbk'));
                globalp=c_char_p(bytes(globalparam,'gbk'));
                jsonparams=c_char_p(bytes(jsonparam,'gbk'));
                begintime=c_char_p(bytes(begintime,'gbk'));
                endtime=c_char_p(bytes(endtime,'gbk')); 
        else:
            thscode=c_char_p(bytes(thscode,'utf8'));
            jsonIndicators=c_char_p(bytes(jsonIndicator,'utf8'));
            globalp=c_char_p(bytes(globalparam,'utf8'));
            jsonparams=c_char_p(bytes(jsonparam,'utf8'));
            begintime=c_char_p(bytes(begintime,'utf8'));
            endtime=c_char_p(bytes(endtime,'utf8'));    
        pIQueryID=c_int(0);
        out=iFinD.c_FTQueryTHS_THS_AsyDateSerialPython(thscode.value,jsonIndicators.value,jsonparams.value,globalp.value,begintime.value,endtime.value,pAsyFunc,pUser,byref(pIQueryID))
        iFinD.c_SetValue(pIQueryID,piQueryID)
        if(out==0):
            global g_FunctionMgr
            global g_Funclock
            g_Funclock.acquire();
            g_FunctionMgr[pIQueryID.value] = CBResultsFunc
            g_Funclock.release()
        return out;

    @staticmethod
    def FTQueryTHS_AsySpecial_ShapePredict(thscode,param,begintime,endtime,CBResultsFunc,pUser,piQueryID):
        if(iFinD.isWin):
            if(iFinD.isless3):
                thscode=c_char_p(thscode);
                param=c_char_p(param);
                begintime=c_char_p(begintime);
                endtime=c_char_p(endtime);
            else:
                thscode=c_char_p(bytes(thscode,'gbk'));
                param=c_char_p(bytes(param,'gbk'));
                begintime=c_char_p(bytes(begintime,'gbk'));
                endtime=c_char_p(bytes(endtime,'gbk')); 
        else:
            thscode=c_char_p(bytes(thscode,'utf8'));
            param=c_char_p(bytes(param,'utf8'));
            begintime=c_char_p(bytes(begintime,'utf8'));
            endtime=c_char_p(bytes(endtime,'utf8'));    
        pIQueryID=c_int(0);
        out=iFinD.c_FTQueryTHS_AsySpecial_ShapePredictPy(thscode.value,param.value,begintime.value,endtime.value,pAsyFunc,pUser,byref(pIQueryID))
        iFinD.c_SetValue(pIQueryID,piQueryID)
        if(out==0):
            global g_FunctionMgr
            global g_Funclock
            g_Funclock.acquire();
            g_FunctionMgr[pIQueryID.value] = CBResultsFunc
            g_Funclock.release()
        return out;
        
    @staticmethod
    def FTQueryTHS_AsytoTHSCODE(transcontents,param,CBResultsFunc,pUser,piQueryID):
        if(iFinD.isWin):
            if(iFinD.isless3):
                transcontents=c_char_p(transcontents);
                param=c_char_p(param);
            else:
                transcontents=c_char_p(bytes(transcontents,'gbk'));
                param=c_char_p(bytes(param,'gbk'));
        else:
            transcontents=c_char_p(bytes(transcontents,'utf8'));
            param=c_char_p(bytes(param,'utf8'));
        pIQueryID=c_int(0);
        out=iFinD.c_FTQueryTHS_AsytoTHSCODEPy(transcontents.value,param.value,pAsyFunc,pUser,byref(pIQueryID))
        iFinD.c_SetValue(pIQueryID,piQueryID)
        if(out==0):
            global g_FunctionMgr
            global g_Funclock
            g_Funclock.acquire();
            g_FunctionMgr[pIQueryID.value] = CBResultsFunc
            g_Funclock.release()
        return out;
        
    @staticmethod
    def FTQueryTHS_AsyrealTimeValuation(transcontents,param,output,CBResultsFunc,pUser,piQueryID):
        if(iFinD.isWin):
            if(iFinD.isless3):
                transcontents=c_char_p(transcontents);
                param=c_char_p(param);
                output=c_char_p(output);
            else:
                transcontents=c_char_p(bytes(transcontents,'gbk'));
                param=c_char_p(bytes(param,'gbk'));
                output=c_char_p(bytes(output,'gbk'));
        else:
            transcontents=c_char_p(bytes(transcontents,'utf8'));
            param=c_char_p(bytes(param,'utf8'));
            output=c_char_p(bytes(output,'utf8'));
        pIQueryID=c_int(0);
        out=iFinD.c_FTQueryTHS_AsyrealTimeValuationPy(transcontents.value,param.value,output.value,pAsyFunc,pUser,byref(pIQueryID))
        iFinD.c_SetValue(pIQueryID,piQueryID)
        if(out==0):
            global g_FunctionMgr
            global g_Funclock
            g_Funclock.acquire();
            g_FunctionMgr[pIQueryID.value] = CBResultsFunc
            g_Funclock.release()
        return out;
        
    @staticmethod
    def FTQueryTHS_AsyfinalValuation(transcontents,param,output,CBResultsFunc,pUser,piQueryID):
        if(iFinD.isWin):
            if(iFinD.isless3):
                transcontents=c_char_p(transcontents);
                param=c_char_p(param);
                output=c_char_p(output);
            else:
                transcontents=c_char_p(bytes(transcontents,'gbk'));
                param=c_char_p(bytes(param,'gbk'));
                output=c_char_p(bytes(output,'gbk'));
        else:
            transcontents=c_char_p(bytes(transcontents,'utf8'));
            param=c_char_p(bytes(param,'utf8'));
            output=c_char_p(bytes(output,'utf8'));
        pIQueryID=c_int(0);
        out=iFinD.c_FTQueryTHS_AsyfinalValuationPy(transcontents.value,param.value,output.value,pAsyFunc,pUser,byref(pIQueryID))
        iFinD.c_SetValue(pIQueryID,piQueryID)
        if(out==0):
            global g_FunctionMgr
            global g_Funclock
            g_Funclock.acquire();
            g_FunctionMgr[pIQueryID.value] = CBResultsFunc
            g_Funclock.release()
        return out;
        
    @staticmethod
    def FTQueryTHS_AsyReportQuery(transcontents,param,output,CBResultsFunc,pUser,piQueryID):
        if(iFinD.isWin):
            if(iFinD.isless3):
                transcontents=c_char_p(transcontents);
                param=c_char_p(param);
                output=c_char_p(output);
            else:
                transcontents=c_char_p(bytes(transcontents,'gbk'));
                param=c_char_p(bytes(param,'gbk'));
                output=c_char_p(bytes(output,'gbk'));
        else:
            transcontents=c_char_p(bytes(transcontents,'utf8'));
            param=c_char_p(bytes(param,'utf8'));
            output=c_char_p(bytes(output,'utf8'));
        pIQueryID=c_int(0);
        out=iFinD.c_FTQueryTHS_AsyReportQueryPy(transcontents.value,param.value,output.value,pAsyFunc,pUser,byref(pIQueryID))
        iFinD.c_SetValue(pIQueryID,piQueryID)
        if(out==0):
            global g_FunctionMgr
            global g_Funclock
            g_Funclock.acquire();
            g_FunctionMgr[pIQueryID.value] = CBResultsFunc
            g_Funclock.release()
        return out;
        
    @staticmethod
    def FTQueryTHS_AsySpecial_StockLink(thscode,param,CBResultsFunc,pUser,piQueryID):
        if(iFinD.isWin):
            if(iFinD.isless3):
                thscode=c_char_p(thscode);
                param=c_char_p(param);
            else:
                thscode=c_char_p(bytes(thscode,'gbk'));
                param=c_char_p(bytes(param,'gbk'));
        else:
            thscode=c_char_p(bytes(thscode,'utf8'));
            param=c_char_p(bytes(param,'utf8'));
        pIQueryID=c_int(0);
        out=iFinD.c_FTQueryTHS_AsySpecial_StockLinkPy(thscode.value,param.value,pAsyFunc,pUser,byref(pIQueryID))
        iFinD.c_SetValue(pIQueryID,piQueryID)
        if(out==0):
            global g_FunctionMgr
            global g_Funclock
            g_Funclock.acquire();
            g_FunctionMgr[pIQueryID.value] = CBResultsFunc
            g_Funclock.release()
        return out;
        
    @staticmethod
    def FTQueryTHS_AsySpecial(type,thscode,param,CBResultsFunc,pUser,piQueryID):
        if(iFinD.isWin):
            if(iFinD.isless3):
                type=c_char_p(type);
                thscode=c_char_p(thscode);
                param=c_char_p(param);
            else:
                type=c_char_p(bytes(type,'gbk'));
                thscode=c_char_p(bytes(thscode,'gbk'));
                param=c_char_p(bytes(param,'gbk'));
        else:
            type=c_char_p(bytes(type,'utf8'));
            thscode=c_char_p(bytes(thscode,'utf8'));
            param=c_char_p(bytes(param,'utf8'));
        pIQueryID=c_int(0);
        out=iFinD.c_FTQueryTHS_AsySpecial_Py(type.value,thscode.value,param.value,pAsyFunc,pUser,byref(pIQueryID))
        iFinD.c_SetValue(pIQueryID,piQueryID)
        if(out==0):
            global g_FunctionMgr
            global g_Funclock
            g_Funclock.acquire();
            g_FunctionMgr[pIQueryID.value] = CBResultsFunc
            g_Funclock.release()
        return out;
        
    @staticmethod
    def FTQueryTHS_Snapshot(thscode,jsonIndicator,jsonparam,begintime,endtime,CBResultsFunc,pUser,piQueryID):
        if(iFinD.isWin):
            if(iFinD.isless3):
                thscode=c_char_p(thscode);
                jsonIndicators=c_char_p(jsonIndicator);
                jsonparams=c_char_p(jsonparam);
                begintime=c_char_p(begintime);
                endtime=c_char_p(endtime);
            else:
                thscode=c_char_p(bytes(thscode,'gbk'));
                jsonIndicators=c_char_p(bytes(jsonIndicator,'gbk'));
                jsonparams=c_char_p(bytes(jsonparam,'gbk'));
                begintime=c_char_p(bytes(begintime,'gbk'));
                endtime=c_char_p(bytes(endtime,'gbk')); 
        else:
            thscode=c_char_p(bytes(thscode,'utf8'));
            jsonIndicators=c_char_p(bytes(jsonIndicator,'utf8'));
            jsonparams=c_char_p(bytes(jsonparam,'utf8'));
            begintime=c_char_p(bytes(begintime,'utf8'));
            endtime=c_char_p(bytes(endtime,'utf8'));     
        pIQueryID=c_int(0);
        out=iFinD.c_FTQueryTHS_SnapshotPy(thscode.value,jsonIndicators.value,jsonparams.value,begintime.value,endtime.value,pAsyFunc,pUser,byref(pIQueryID))
        iFinD.c_SetValue(pIQueryID,piQueryID)
        if(out==0):
            global g_FunctionMgr
            global g_Funclock
            g_Funclock.acquire();
            g_FunctionMgr[pIQueryID.value] = CBResultsFunc
            g_Funclock.release()
        return out;

    @staticmethod
    def FTQueryTHS_EDBQuery(indicators, begintime, endtime,CBResultsFunc,pUser,piQueryID):
        if(iFinD.isWin):
            if(iFinD.isless3):
                indicators=c_char_p(indicators);
                begintime=c_char_p(begintime);
                endtime=c_char_p(endtime);
            else:
                indicators=c_char_p(bytes(indicators,'gbk'));
                begintime=c_char_p(bytes(begintime,'gbk'));
                endtime=c_char_p(bytes(endtime,'gbk')); 
        else:
            indicators=c_char_p(bytes(indicators,'utf8'));
            begintime=c_char_p(bytes(begintime,'utf8'));
            endtime=c_char_p(bytes(endtime,'utf8'));   
        pIQueryID=c_int(0);
        out=iFinD.c_FTQueryTHS_EDBQueryPy(indicators.value,begintime.value,endtime.value,pAsyFunc,pUser,byref(pIQueryID))
        iFinD.c_SetValue(pIQueryID,piQueryID)
        if(out==0):
            global g_FunctionMgr
            global g_Funclock
            g_Funclock.acquire();
            g_FunctionMgr[pIQueryID.value] = CBResultsFunc
            g_Funclock.release()
        return out;
        
    @staticmethod
    def FTQueryTHS_EDB(indicators, param, begintime, endtime,CBResultsFunc,pUser,piQueryID):
        if(iFinD.isWin):
            if(iFinD.isless3):
                indicators=c_char_p(indicators);
                param=c_char_p(param)
                begintime=c_char_p(begintime);
                endtime=c_char_p(endtime);
            else:
                indicators=c_char_p(bytes(indicators,'gbk'));
                param=c_char_p(bytes(param,'gbk'));
                begintime=c_char_p(bytes(begintime,'gbk'));
                endtime=c_char_p(bytes(endtime,'gbk')); 
        else:
            indicators=c_char_p(bytes(indicators,'utf8'));
            param=c_char_p(bytes(param,'utf8'));
            begintime=c_char_p(bytes(begintime,'utf8'));
            endtime=c_char_p(bytes(endtime,'utf8'));   
        pIQueryID=c_int(0);
        out=iFinD.c_FTQueryTHS_EDBQueryPy(indicators.value,param.value,begintime.value,endtime.value,pAsyFunc,pUser,byref(pIQueryID))
        iFinD.c_SetValue(pIQueryID,piQueryID)
        if(out==0):
            global g_FunctionMgr
            global g_Funclock
            g_Funclock.acquire();
            g_FunctionMgr[pIQueryID.value] = CBResultsFunc
            g_Funclock.release()
        return out;

    @staticmethod
    def FTQuanyTHS_iwencai(query,domain,CBResultsFunc,pUser,piQueryID):
        if(iFinD.isWin):
            if(iFinD.isless3):
                indicators=c_char_p(query);
                begintime=c_char_p(domain);
            else:
                indicators=c_char_p(bytes(query,'gbk'));
                begintime=c_char_p(bytes(domain,'gbk')); 
        else:
            indicators=c_char_p(bytes(query,'utf8'));
            begintime=c_char_p(bytes(domain,'utf8')); 
        pIQueryID=c_int(0);
        out=iFinD.c_FTQueryTHS_iwencaiPy(indicators.value,begintime.value,pAsyFunc,pUser,byref(pIQueryID))
        iFinD.c_SetValue(pIQueryID,piQueryID)
        if(out==0):
            global g_FunctionMgr
            global g_Funclock
            g_Funclock.acquire();
            g_FunctionMgr[pIQueryID.value] = CBResultsFunc
            g_Funclock.release()
        return out;
        
    @staticmethod
    def FTQuanyTHS_WCQuery(query,domain,CBResultsFunc,pUser,piQueryID):
        if(iFinD.isWin):
            if(iFinD.isless3):
                indicators=c_char_p(query);
                begintime=c_char_p(domain);
            else:
                indicators=c_char_p(bytes(query,'gbk'));
                begintime=c_char_p(bytes(domain,'gbk')); 
        else:
            indicators=c_char_p(bytes(query,'utf8'));
            begintime=c_char_p(bytes(domain,'utf8')); 
        pIQueryID=c_int(0);
        out=iFinD.c_FTQueryTHS_WCQueryPy(indicators.value,begintime.value,pAsyFunc,pUser,byref(pIQueryID))
        iFinD.c_SetValue(pIQueryID,piQueryID)
        if(out==0):
            global g_FunctionMgr
            global g_Funclock
            g_Funclock.acquire();
            g_FunctionMgr[pIQueryID.value] = CBResultsFunc
            g_Funclock.release()
        return out;

    @staticmethod
    def FTQueryTHS_QuotesPushing(thscode,indicator,Callback):
        import json
        """实时行情"""
        global nRegRTID
        if(iFinD.isWin):
            if(iFinD.isless3):
                thscode=c_char_p(thscode);
                jsonIndicators=c_char_p(indicator);
                jsonparams=c_char_p('');
            else:
                thscode=c_char_p(bytes(thscode,'gbk'));
                jsonIndicators=c_char_p(bytes(indicator,'gbk'));
                jsonparams=c_char_p(bytes('','gbk'));
        else:
            thscode=c_char_p(bytes(thscode,'utf-8'));
            jsonIndicators=c_char_p(bytes(indicator,'utf-8'));
            jsonparams=c_char_p(bytes('','utf-8'));
        add=c_bool(1);
        RegId=c_int32(nRegRTID);
        out=-1
        global pRealTimeFunc
        if not callable(Callback):
            out=iFinD.C_FTQueryTHS_AsynRTByJsonPy(thscode.value,jsonIndicators.value,jsonparams.value,add,pRealTimeFunc,c_void_p(0),byref(RegId));
        else:
            if (type(Callback) == type(pRealTimeFunc)):
                out=iFinD.C_FTQueryTHS_AsynRTByJsonPy(thscode.value,jsonIndicators.value,jsonparams.value,add,Callback,c_void_p(0),byref(RegId));
            pRealTimeFunc=CMPTHSREALTIMEFUNC(Callback)
            out=iFinD.C_FTQueryTHS_AsynRTByJsonPy(thscode.value,jsonIndicators.value,jsonparams.value,add,pRealTimeFunc,c_void_p(0),byref(RegId));
        nRegRTID=RegId.value;
        return out;

    @staticmethod
    def FTQueryTHS_UnQuotesPushing(thscode,indicator):
        import json
        """实时行情"""
        global nRegRTID
        if(iFinD.isWin):
            if(iFinD.isless3):
                thscode=c_char_p(thscode);
                jsonIndicators=c_char_p(indicator);
                jsonparams=c_char_p('');
            else:
                thscode=c_char_p(bytes(thscode,'gbk'));
                jsonIndicators=c_char_p(bytes(indicator,'gbk'));
                jsonparams=c_char_p(bytes('','gbk'));
        else:
            thscode=c_char_p(bytes(thscode,'utf-8'));
            jsonIndicators=c_char_p(bytes(indicator,'utf-8'));
            jsonparams=c_char_p(bytes('','utf-8'));
        add=c_bool(0);
        RegId=c_int32(nRegRTID);
        out=iFinD.C_FTQueryTHS_AsynRTByJsonPy(thscode.value,jsonIndicators.value,jsonparams.value,add,pRealTimeFunc,c_void_p(0),byref(RegId));
        nRegRTID=RegId.value;
        return out;

    @staticmethod
    def FT_DataStastics(outflag=False):
        """查询流量"""
        import json
        ptr=iFinD.C_FT_ifinDDataStatissticsPy();
        out = cast(ptr,c_char_p).value
        if outflag == False:
            out=json.loads(out.decode(iFinD.decodeMethod));
        iFinD.c_DeleteMm(ptr);
        return out;

    @staticmethod
    def FT_GetErrorInfo(errorcode,outflag=False):
        """查询error"""
        import json
        Error=c_int32(errorcode);
        ptr=iFinD.C_FT_ifinDErrorMsg(Error);
        out = cast(ptr,c_char_p).value
        if outflag == False:
            out=json.loads(out.decode(iFinD.decodeMethod));
        iFinD.c_DeleteMm(ptr);
        return out;

    @staticmethod
    def FT_DateQuery(exchange, params, begintime, endtime, outflag=False):
        """查询Datequery"""
        import json
        if(iFinD.isWin):
            if(iFinD.isless3):
                Exchange=c_char_p(exchange);
                Params=c_char_p(params);
                Begintime=c_char_p(begintime);
                Endtime=c_char_p(endtime);
            else:
                Exchange=c_char_p(bytes(exchange,'utf8'))
                Params=c_char_p(bytes(params,'utf8'))
                Begintime=c_char_p(bytes(begintime,'utf8'))
                Endtime=c_char_p(bytes(endtime,'utf8'))
        else:
            Exchange=c_char_p(bytes(exchange,'utf8'))
            Params=c_char_p(bytes(params,'utf8'))
            Begintime=c_char_p(bytes(begintime,'utf8'))
            Endtime=c_char_p(bytes(endtime,'utf8'))
        ptr=iFinD.C_FT_ifinDDateQuery(Exchange.value, Params.value, Begintime.value, Endtime.value);
        out = cast(ptr,c_char_p).value
        if outflag == False:
            out=json.loads(out.decode(iFinD.decodeMethod));
        iFinD.c_DeleteMm(ptr);
        return out;

    @staticmethod
    def FT_Date_Query(exchange, params, begintime, endtime, format='format:str'):
        """查询Datequery(新)"""
        import json
        if(iFinD.isWin):
            if(iFinD.isless3):
                Exchange=c_char_p(exchange);
                Params=c_char_p(params);
                Begintime=c_char_p(begintime);
                Endtime=c_char_p(endtime);
            else:
                Exchange=c_char_p(bytes(exchange,'utf8'))
                Params=c_char_p(bytes(params,'utf8'))
                Begintime=c_char_p(bytes(begintime,'utf8'))
                Endtime=c_char_p(bytes(endtime,'utf8'))
        else:
            Exchange=c_char_p(bytes(exchange,'utf8'))
            Params=c_char_p(bytes(params,'utf8'))
            Begintime=c_char_p(bytes(begintime,'utf8'))
            Endtime=c_char_p(bytes(endtime,'utf8'))
        ptr=iFinD.C_FT_ifinDDate_Query(Exchange.value, Params.value, Begintime.value, Endtime.value);
        result = cast(ptr,c_char_p).value
        data = THSData()
        data.formatResultDate(result,format)
        iFinD.c_DeleteMm(ptr);
        return data;
        
    @staticmethod
    def FT_DateOffset(exchange, params, endtime, outflag=False):
        """查询Dateoffset"""
        import json
        if(iFinD.isWin):
            if(iFinD.isless3):
                Exchange=c_char_p(exchange);
                Params=c_char_p(params);
                Endtime=c_char_p(endtime);
            else:
                Exchange=c_char_p(bytes(exchange,'gbk'))
                Params=c_char_p(bytes(params,'gbk'))
                Endtime=c_char_p(bytes(endtime,'gbk'))
        else:
            Exchange=c_char_p(bytes(exchange,'utf8'))
            Params=c_char_p(bytes(params,'utf8'))
            Endtime=c_char_p(bytes(endtime,'utf8'))
        ptr=iFinD.C_FT_ifinDDateOffset(Exchange.value, Params.value, Endtime.value);
        out = cast(ptr,c_char_p).value
        if outflag == False:
            out=json.loads(out.decode(iFinD.decodeMethod));
        iFinD.c_DeleteMm(ptr);
        return out;
        
    @staticmethod
    def FT_Date_Offset(exchange, params, endtime, format='format:str'):
        """查询Dateoffset"""
        import json
        if(iFinD.isWin):
            if(iFinD.isless3):
                Exchange=c_char_p(exchange);
                Params=c_char_p(params);
                Endtime=c_char_p(endtime);
            else:
                Exchange=c_char_p(bytes(exchange,'gbk'))
                Params=c_char_p(bytes(params,'gbk'))
                Endtime=c_char_p(bytes(endtime,'gbk'))
        else:
            Exchange=c_char_p(bytes(exchange,'utf8'))
            Params=c_char_p(bytes(params,'utf8'))
            Endtime=c_char_p(bytes(endtime,'utf8'))
        ptr=iFinD.C_FT_ifinDDate_Offset(Exchange.value, Params.value, Endtime.value);
        result = cast(ptr,c_char_p).value
        data = THSData()
        data.formatResultDate(result,format)
        iFinD.c_DeleteMm(ptr);
        return data;

    @staticmethod
    def FT_DateCount(exchange, params, begintime, endtime, outflag=False):
        """查询DateCount"""
        import json
        if(iFinD.isWin):
            if(iFinD.isless3):
                Exchange=c_char_p(exchange);
                Params=c_char_p(params);
                Begintime=c_char_p(begintime);
                Endtime=c_char_p(endtime);
            else:
                Exchange=c_char_p(bytes(exchange,'gbk'))
                Params=c_char_p(bytes(params,'gbk'))
                Begintime=c_char_p(bytes(begintime,'gbk'))
                Endtime=c_char_p(bytes(endtime,'gbk'))
        else:
            Exchange=c_char_p(bytes(exchange,'utf8'))
            Params=c_char_p(bytes(params,'utf8'))
            Begintime=c_char_p(bytes(begintime,'utf8'))
            Endtime=c_char_p(bytes(endtime,'utf8'))
        ptr=iFinD.C_FT_ifinDDateCount(Exchange.value, Params.value, Begintime.value, Endtime.value);
        out = cast(ptr,c_char_p).value
        if outflag == False:
            out=json.loads(out.decode(iFinD.decodeMethod));
        iFinD.c_DeleteMm(ptr);
        return out;

class w(object):
    @classmethod
    def wsi(cls,thscode, jsonIndicator,begintime, endtime,jsonparam):
       return iFinD.FTQuerySynTHS_HighFrequenceSequence(thscode, jsonIndicator, jsonparam, begintime, endtime);
