# _*_ coding:utf-8 _*_
__author__ = 'Fxd'

from datetime import datetime
import time
import json
import os
from pymongo.read_preferences import Primary
import asyncio
import functools
from ConfigDB import aliMongo, RedisDb, getProxies
TranslationRedisKey = "Translation_Content"
import httpx
# 代理服务器
proxyHost = "http-dyn.abuyun.com"
proxyPort = "9020"
RPC_ID = 'MkEWBc'
#声明一个类用来处理翻译的数据
class TranslationDataParse(object):

    # 将相同语种的数据打包
    def getPackageData(self,dataList):
        dicValue=eval(dataList)
        TargetLanguage=dicValue["TargetLanguage"]
        content=dicValue["Content"]
        unionKeys={}
        UniqueId=dicValue["UniqueId"]
        keys=[]
        data=''
        for key in content:
            keys.append(key)
            if content[key]:
                data +=content[key]+"\n[+]\n"
            else:
                data+=""+"\n[+]\n"
        unionKeys[UniqueId]=keys
        #把<br />换成/n否则谷歌翻译识别错乱
        data=data.replace("\\n","\n").replace("<br />","\n[-]\n").replace("<br/>","\n[-]\n").replace("< br />","\n[-]\n")
        return data,unionKeys,TargetLanguage,UniqueId


    #大于5000个字符对文档进行切片翻译
    def getPageWords(self,transContent):
        content=transContent
        transList=[]
        wordCount=len(transContent)
        endLength=0
        if(wordCount>5000):
            while len (content)>0 :
                if len(content)<5000:
                    transList.append(content)
                    return transList
                tempWord=transContent[0:5000]
                endLength=tempWord.rfind(".")+1
                if(endLength==-1):
                    endLength=tempWord.rfind(",")+1
                contentData=tempWord[0:endLength]
                transList.append(contentData)
                content=transContent[endLength:]
        else:
            transList.append(transContent)
        return transList  

    #解析翻译结果
    def parseResult(self,transContent,TransKeys):
        transContent=transContent.replace("{ 0}","{0}").replace("{0 }","{0}").replace("{ 0 }","{0}")
        transContent=transContent.replace("[ +]","[+]").replace("[+ ]","[+]").replace("[ + ]","[+]")
        # datalist=transContent.split("{0}")[:-1]
        result={}
        lines=transContent.split("[+]")[:-1]
        keylist=list(TransKeys.keys())
        unionId=keylist[0]
        for (i,key) in enumerate(TransKeys[unionId]):
            result[key]=lines[i].strip()
        dateNow = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        #更新到mongodb
        aliMongo.update_many({"UniqueId": unionId}, {'$set': {'Status': 1, 'Result': result, 'LastModificationTime': dateNow,"Version":2}})
        print("ok...", unionId, "...", dateNow)

    # 新版谷歌翻译
    def getTranslate(self, source, target, content):
        try:
            if len(content) == 0:
                return ""
            proxies=getProxies()

            paramers={"rpcids": "MkEWBc","f.sid": 7401784699531058895,"bl": "boq_translate-webserver_20211019.14_p0","hl": "zh-CN","soc-app": 1,"soc-platform": 1,"soc-device": 1,"_reqid": 2238458,"rt": "c"}

            postdata = {
                "f.req": self._build_rpc_request(content, source, target),
            }
            # 将参数编码
            #requestData = urlencode(postdata, doseq=True).encode("utf-8")
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0 Safari/537.36",
                "Content-Type":"application/x-www-form-urlencoded;charset=UTF-8",
                "Referer":"https://translate.google.cn/"
            }
            #设置cookie可以一定程度防止无法采集
            cookies={"NID":"224%3DXwM3ey2NHch21kMpiADcWNJt0vIjGlS8ormlmJDQHR_Du8uryDiTvxV_dcV5RknEItelXRn7SnY8kQDv2ceKyHJQdIYOV2Gs6woio1ilXXmxeMYbqUKRRkQ8uYHHyEMOD-31EzEKipZ7cvp575OSIhhUOIepWCQ-FgxEXyqRLXo"}
            url="https://translate.google.cn/_/TranslateWebserverUi/data/batchexecute"
            result=''
            with httpx.Client(proxies=proxies)as client:
                request=client.post(url,data=postdata,headers=headers,timeout=20)
                result = self.getData(request.text)
            return result
        except Exception as e:
            # print(e)
            return ''
    #旧方法处理大于5000个字符的翻译
    def get_world_page(self, context, TourceLanguage, TargetLanguage):
        str = ""
        languageDict = {"DEU": "de", "ESN": "es", "FRA": "fr", "ITA": "it", "JPN": "ja", "IN": "hi", "UK": "en", "IND": "id",
                        "THA": "th", "ZH": "zh-CN", "NLD": "nl", "PL": "pl", "PT": "pt", "SA": "ar", "EN": "en", "SE": "sv", "TR": "tr", "KO": "ko"}
        if len(context) > 5000:
            newlist = self.get_string(context, ".")
            count = 0
            for item in newlist:
                count += 1
                if count != len(newlist):
                    if isinstance(item, list):
                        item = ""
                    else:
                        item = item+""
                str += self.getTranslate(languageDict[TourceLanguage],
                                         languageDict[TargetLanguage], item)
        else:
            str = self.getTranslate(
                languageDict[TourceLanguage], languageDict[TargetLanguage], context)
        return str

    # 处理解析到的数据
    def getData(self, data): 
        RPC_ID = 'MkEWBc'
        token_found = False
        square_bracket_counts = [0, 0]
        resp = ''
        for line in data.split('\n'):
            token_found = token_found or f'"{RPC_ID}"' in line[:30]
            if not token_found:
                continue
            is_in_string = False
            for index, char in enumerate(line):
                if char == '\"' and line[max(0, index - 1)] != '\\':
                    is_in_string = not is_in_string
                if not is_in_string:
                    if char == '[':
                        square_bracket_counts[0] += 1
                    elif char == ']':
                        square_bracket_counts[1] += 1

            resp += line
            if square_bracket_counts[0] == square_bracket_counts[1]:
                break
        parsed = {}
        try:
            dataList = json.loads(resp)
            parsed = json.loads(dataList[0][2])
        except Exception as e:
            pass
        datalislist =list((map(lambda part: part[0], parsed[1][0][0][5])))
        result = ''
        if len(datalislist) > 1:
            for row in datalislist:
                if '\n' not in row:
                    row=row+"\n"
                result+=row
        else:
            result =''.join(datalislist)
        # not sure
        return result

    # 处理发送的data数据
    def _build_rpc_request(self, data: str, source: str, target: str):
        return json.dumps([[
            [
                RPC_ID,
                json.dumps([[data, source, target, True], [None]],
                           separators=(",", ":")),
                None,
                "generic",
            ],
        ]], separators=(",", ":"))

async def TranslationMain(TranslationData):
    if TranslationData:
        Content = {}
        translation=TranslationDataParse()
        TransDataPakge= translation.getPackageData(TranslationData)
        TransData=TransDataPakge[0]
        TransKeys=TransDataPakge[1]
        TargetLanguage=TransDataPakge[2]
        TourceLanguage = "EN"
        value=TransData
        value=TransData.replace('.<br', '. <br').replace("&#39;", "'").replace("&nbsp;", "&nbsp/").replace("&amp;","&").replace("&lt;", "<").replace("&deg;", "。").replace("&plusmn;", "±").replace("&quot;", '"').replace("&rsquo;", "’").replace("&times;", "×").replace("&gt;", ">").replace("&reg;", "®").replace("&ldquo;", '“').replace("&rdquo;", '”').replace("&le;", "≤").replace("&ndash;", "–").replace("&eacute;", "É").replace("&shy;", "").replace("&mdash;", "—").replace("&Omega;", "Ω").replace("&omega;", "ω").replace("&ge;", "≥").replace("&mu;", "μ").replace("&radic;", "√").replace("&middot;", "·").replace("&lsquo;", "‘").replace("&iacute;", "í").replace("&phi;", "φ").replace("&Phi;", "Φ").replace("&egrave;", "è").replace("&ucirc;", "û").replace("&asymp;", "≈").replace("&Otilde;", "Õ").replace("&sup2;", "²").replace("&hellip;", "…").replace("&prime;","′").replace("&Prime;","″").replace("&frasl;", "⁄").replace("&ordm;", "º").replace("&#39;", " ").replace("&sup3;", "³").replace("&acute;", "´").replace("&sup;", "⊃").replace("&crarr;", "↵").replace("&or;", "∨").replace("&pound;", "£").replace("&not;", "¬").replace("&lambda;", "λ").replace("&Oslash;", "Ø").replace("&oslash;", "ø").replace("&bull;", "•").replace("&epsilon;", "ε").replace("&Epsilon;","Ε").replace("&alpha;", "α").replace("&mdash;", "—").replace("&ccedil;", "ç").replace("&frac14;","¼").replace("&aacute;", "á").replace("&rarr;", "→").replace("&micro;", "µ").replace("&trade;", "™").replace("&diams;", "♦").replace("&iuml;", "ï").replace("&eta;", "η").replace("&nu;", "ν").replace("&iota;", "ι").replace("&kappa;", "κ").replace("&acirc;", "â").replace("&Acirc;", "Â").replace("&ntilde;", "ñ").replace("&ecirc;", "ê").replace("amp;", "&").replace("&Sigma;", "Σ").replace("&frac12;", "½").replace("&permil;", "‰").replace("&cent;", "¢").replace("&agrave;","à").replace("&Agrave;", "À").replace("&scaron;", "š").replace("&Scaron;", "Š").replace("&aring;","å").replace("&Aring;", "Å").replace("&uuml;", "ü").replace("&Uuml;", "Ü").replace("&frac34;", "¾").replace("&ouml;", "ö").replace("&Ouml;", "Ö").replace("&euro;", "€").replace("&iexcl;", "¡").replace("&laquo;", "«").replace("&infin;", "∞").replace("&oacute;", "ó").replace("&Oacute;","Ó").replace("&ensp;", " ").replace("&ordf;", "").replace("&harr;", "↔").replace("&hArr;", "⇔").replace("&#x2713; ", " ").replace("&bdquo;", "„").replace("&fnof;", "ƒ").replace("&atilde;", "ã").replace("&Atilde;","Ã").replace("&empty;", "∅").replace("&#x3A9;", " ").replace("&#034;", " ").replace("&macr;", "¯").replace("&auml;", "ä").replace("&Auml;", "Ä").replace("&uacute;", "ú").replace("&Uacute;", "Ú").replace("&euml;", "ë").replace("&Euml;", "Ë").replace("&icirc;", "î").replace("&Icirc;", "Î").replace("&lrm;", "").replace("&copy;", "©").replace("&Delta;", "Δ").replace("&delta;", "δ").replace("&rdquo; ", '”').replace("&igrave;", "ì").replace("&Igrave;", "Ì").replace("&darr;", "↓").replace("&dArr;", "⇓").replace("&tilde;", "˜").replace("&szlig;", "ß").replace("&iuml;", "ï").replace("&Iuml;", "Ï").replace("&OElig;", "Œ").replace("&oelig;", "œ").replace("&#8451;", " ").replace("&uml;", "¨").replace("&ocirc;", "ô").replace("&Ocirc;", "Ô").replace("&zwnj;", "").replace("&#x27;", " ").replace("&#96;", " ")
        datacontent=translation.getPageWords(value)
        allContent=''
        for data in datacontent:
            #翻译三次
            future = asyncio.get_event_loop().run_in_executor(None, functools.partial(translation.get_world_page, data, TourceLanguage, TargetLanguage))
            TranslationResult = await future
            if TranslationResult == "":
                # #失败则更新InRedis
                # UniqueId=TransDataPakge[3]
                # aliMongo.update_many({"UniqueId": UniqueId}, {'$set': {'InRedis': None}})
                return
            TranslationResult = TranslationResult.replace("<B>","<b>").replace("</B>","</b>").replace("< / span>", "</span>").replace("> />", ">").replace("& amp;", "&amp;").replace("</ b>", "</b>").replace("? </ B>", "?</b>").replace("</ strong>", "</strong>").replace("</ b >", "</b>").replace("& nbsp / ", "&nbsp;").replace("<!-- b-->", "</b>").replace("& nbsp /", "&nbsp;")
            TranslationResult=TranslationResult.replace("[ ","[").replace(" ]","]").replace("[ + ]","[+]").replace("[ +]","[+]").replace("[+ ]","[+]")
            TranslationResult=TranslationResult.replace("</ B>","</b>").replace("\n[-]\n","<br />").replace("[-]","<br />").replace("\n[ - ]\n","<br />").replace("[ - ]","<br />").replace("\n[ -]\n","<br />").replace("[ -]","<br />").replace("\n[- ]\n","<br />").replace("[- ]","<br />")
            
            allContent+=TranslationResult
        translation.parseResult(allContent,TransKeys)
        if Content == {}:
            return

#退出上次进程
def exitsProcess():
    try:
      # 判断当前文件名称的pid是否存在，如果存在根据pid杀死之前的程序
        pyName=os.path.basename(__file__).replace("py","")
        path="./Pid"
        #如果文件夹不存在创建一个文件夹
        if not os.path.exists(path):
            os.mkdir(path)
        pidPath=path+'/'+pyName+"pid"
        # #如果存在，根据pid杀死程序
        if os.path.exists(pidPath):
            with open(pidPath,'r') as file:
                pid=int(file.read())
                if(pid>0):
                    find_kill = 'taskkill -f -pid %s' % pid
                    
                    result = os.popen(find_kill)
        # #创建当前程序的pid
        pid=os.getpid()
        with open(pidPath,'w+') as file:
            file.write(str(pid))
        print("杀死进程成功")
    except Exception as e:
        print(e)


#删除进程文件
def delPidPath():
    pyName=os.path.basename(__file__).replace("py","")
    path="./Pid/"+pyName+"pid"
    os.remove(path)

secend=1
if __name__ == '__main__':
    try:
        exitsProcess()
        while True:
            queueCount = RedisDb.llen(TranslationRedisKey)
            if queueCount > 0:
                secend=1
                TranslationDatas = []
                [TranslationDatas.append(RedisDb.rpop(TranslationRedisKey)) for i in
                range(10 if queueCount > 10 else queueCount)]
                tasks = [TranslationMain(TranslationData) for TranslationData in TranslationDatas]
                loop = asyncio.get_event_loop()
                loop.run_until_complete(asyncio.wait(tasks))
            else:
                secend=10
            time.sleep(secend)   
    except Exception as e:
        delPidPath()
        os._exit()
    time.sleep(1)
