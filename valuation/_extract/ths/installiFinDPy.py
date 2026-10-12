# -*- coding: cp936 -*-
import sys
import os
"""
版本：1.0.0.1
作者：邓猛 dengmeng@myhexin.com 时间：20141106
更新时间：20141106 增加数据接口
文档介绍：iFinD Python接口程序。需与FTDataInterface.dll一起使用
修改历史：
版权：同花顺iFinD
"""

def installiFinDPy():
    version=sys.version
    print(version);
    verss=version.split()[0].split('.');
    ver=int(verss[0])+float(verss[1])/10;
    bit=int(version.split(' bit ')[0].split()[-1]);

    #if(len(sys.argv)<=1):
        #print('No iFinDPy path!');
        #return;
    #print(sys.argv[1:])

    if(len(sys.argv)<=1):
        srcpath=sys.path[0]
        srcpath=os.path.dirname(srcpath)
    else:
        srcpath=sys.argv[1]
    if not (srcpath.endswith('\\') or srcpath.endswith('//')):
        srcpath=srcpath+'\\'
        
    #sitepath=".";
    try:
        #Python3
        import sysconfig
        sitepath = sysconfig.get_paths()["purelib"]
    except ImportError:
        #Python2
        from distutils.sysconfig import get_python_lib
        sitepath = get_python_lib()
    #for x in sys.path:
        #ix=x.find('site-packages')
        #if( ix>=0 and x[ix:]=='site-packages'):
          #sitepath=x;
          #break;

    filepath=sitepath+"\\iFinDPy.pth"
    #print(sitepath);    

    if(ver<2.6):
       print('Error: Python version must be >=2.6!')
       return;

    if(bit==64 ):
       print('Python is 64 bits')
       srcpath=srcpath+"x64"
    else:#if(bit==64 ):
       print('Python is 32 bits')
       srcpath=srcpath+"x86"

    #print(srcpath);
    sitefile=open(filepath,'w');
    sitefile.writelines(srcpath)
    sitefile.close();
    print('Installed into'),
    print(sitepath),
    print('OK!');
    
    

installiFinDPy()
