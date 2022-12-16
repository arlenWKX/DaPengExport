import requests, requests.utils
import os
import re
from pyaria2 import *
from time import sleep
import subprocess
from lxml import etree
from random import randint
import json
import configparser

ua = {
    "user-agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Safari/537.36 Edg/106.0.1370.37"
}

main_ini_default = """
[user]
account=你的大鹏账户名/手机号
password=你的密码
cookie=
[download]
dir=保存目录 ( 默认: D:\DaPengExport )
"""


class Crawler:

    def __init__(self):
        self.session = requests.session()
        self.session.headers.update({
            "user-agent":
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Safari/537.36 Edg/106.0.1370.37"
        })
        self.data = []
        self.conf = configparser.ConfigParser()
        try:
            self.conf.read('config\\main.ini')
            self.account = self.conf.get("user", "account")
            self.password = self.conf.get("user", "password")
            if self.conf.has_option("download", "dir"):
                self.downdir = self.conf.get("download", "dir")
            else:
                self.downdir = 'D:\DaPengExport'
            if not os.path.exists ( self.downdir ):
                os.makedirs ( self.downdir )
            if not self.conf.has_option("user", "cookie") or self.conf.get("user", "cookie") == "":
                self.loginsub()
                self.conf.set("user", "cookie",
                              json.dumps(json.dumps(self.session.cookies.get_dict())))
            else:
                self.session.cookies = requests.utils.cookiejar_from_dict(
                    json.loads(self.conf.get("user", "cookie")))
            self.session.headers.update({
                "host": "www.dapengjiaoyu.cn",
                "Referer": "https://www.dapengjiaoyu.cn/personal-center/course/formal",
            })
            res = self.session.get("https://www.dapengjiaoyu.cn/dp-course/api/users/details")
            if res.status_code != 200:
                if res.status_code == 403:
                    print("登陆失败:", res.json()['msg'])
                else:
                    print("登陆失败:", res.status_code)
                return False
            return True
        except FileNotFoundError:
            print("读取配置失败: 未找到配置文件. 自动生成空白文件, 请填写后重试.")
            with open('config\\main.ini') as main_ini:
                main_ini.write(main_ini_default)
            return False
        except (configparser.NoSectionError, configparser.NoOptionError):
            print("读取配置失败: 配置错误")
            return False
        except requests.exceptions.RequestException:
            print("登陆失败: 网络错误")
            return False

    def loginsub(self):
        self.session.post(
            url="https://passport.dapengjiaoyu.cn/account-login",
            data={
                "account": self.account,
                "password": self.password,
                "source": "NORMALLOGIN",
                "type": "USERNAME",
                "responseType": "JSON",
                "sourceType": "PC",
            },
            headers={
                "host": "passport.dapengjiaoyu.cn",
                "Referer": "https://passport.dapengjiaoyu.cn/pc/login?otherLogin=true",
                "Origin": "https://passport.dapengjiaoyu.cn",
            },
        )
        self.session.get(
            "https://passport.dapengjiaoyu.cn/oauth/authorize?response_type=code&client_id=Dd8fbbB5&redirect_uri=//www.dapengjiaoyu.cn/callback&state=1"
        )

    def job(self, m3u8_url, key_url, vtitle, download_dir):
        print("开始下载", m3u8_url)
        print(m3u8_url, "->", download_dir)
        sleeptime = 1
        client = Aria2RPC(token="dapengexp")
        if not os.path.exists(download_dir + "ts/"):
            os.makedirs(download_dir + "ts/")
        m3u8_data = requests.get(m3u8_url, headers=ua).text
        with open(download_dir + "ts/key.key", "wb") as out:
            out.write(requests.get(key_url, headers=ua).content)
        ts_urls = re.findall(r"(https:.*?\.ts)", m3u8_data)
        jobs = []
        for index, ts in enumerate(ts_urls):
            m3u8_data = m3u8_data.replace(ts, f"{index}.ts")
            print(f"使用{'https://' + proxies[randint(0,len(proxies) - 1)]}下载{index}.ts")
            jobs.append((
                client.addUri(
                    [ts], {
                        "dir": download_dir + "ts/",
                        "out": str(index) + ".ts",
                        "all-proxy": 'https://' + proxies[randint(0,
                                                                  len(proxies) - 1)]
                    }),
                index,
                ts,
            ))
        for x, index, ts in jobs:
            while True:
                y = client.tellStatus(x)["status"]
                if y == "complete":
                    if sleeptime > 1:
                        sleeptime = sleeptime / 1.2
                    break
                elif y == "error":
                    sleeptime = sleeptime * 1.44
                    print(f"下载 {index}.ts 时出现错误, {sleeptime} 秒内重试.")
                    client.pauseAll()
                    sleep(sleeptime)
                    client.unpauseAll()
                    xx = client.addUri(
                        [ts],
                        {
                            "dir": download_dir + "ts/",
                            "out": str(index) + ".ts",
                            "max-connection-per-server": 1,
                            "split": 1,
                            "max-concurrent-downloads": 1,
                            "continue": "false",
                            "all-proxy": 'https://' + proxies[randint(0,
                                                                      len(proxies) - 1)]
                        },
                    )
                    if client.tellStatus(xx)["status"] == "error":
                        sleeptime = sleeptime * 2.0736
                        print(f"下载 {index}.ts 时仍出现错误, 使用 requests.get() 重试.")
                        with open(download_dir + "ts/" + str(index) + ".ts", "wb") as file:
                            while True:
                                addr = proxies[randint(0, len(proxies) - 1)]
                                resp = requests.get(url=ts,
                                                    stream=True,
                                                    headers=ua,
                                                    proxies={
                                                        "http": "http://" + addr,
                                                        "https": "http://" + addr
                                                    })
                                if resp.status_code != 403:
                                    for chunk in resp.iter_content(chunk_size=1024):
                                        if chunk:
                                            file.write(chunk)
                                    break
                                sleep(sleeptime=sleeptime + 1)
                    break
                sleep(1)
        m3u8_data = m3u8_data.replace(key_url, "key.key")
        with open(download_dir + "ts/index.m3u8", "w") as out:
            out.write(m3u8_data)
        print("Encoding...")
        subprocess.run(
            f'bin\\ffmpeg.exe -allowed_extensions ALL -i "{download_dir}ts/index.m3u8" -c copy -vtag hvc1 "{download_dir+vtitle}.mp4" -v fatal -y && rd /s /q "{download_dir}ts"',
            shell=True,
        )

    def get_all(self):
        res = self.session.get(
            "https://www.dapengjiaoyu.cn/api/old/courses/college?source=PC").json()
        for collage in res:
            res1 = self.session.get(
                "https://www.dapengjiaoyu.cn/api/old/courses/open?type=VIP&collegeId=" +
                collage["id"]).json()
            for course in res1:
                vod = self.session.get("https://www.dapengjiaoyu.cn/api/old/courses/" +
                                       course["id"] + "/vods").json()
                for section in vod["courseVodContents"]:
                    for lecture in section["lectures"]:
                        vid = lecture["videoContent"]["vid"][0:-2]
                        self.job(
                            f"https://hls.videocc.net/{vid[:10]}/{vid[-1]}/{vid}_3.m3u8",
                            f"https://hls.videocc.net/{vid[:10]}/{vid[-1]}/{vid}_3.key",
                            lecture["videoContent"]["title"],
                            f"D:/DapengExport/{collage [ 'name' ]}/{course [ 'title' ]}/{section [ 'title' ]}/{lecture [ 'title' ]}/"
                        )


def addproxy(tdlist):
    global proxies
    for td in tdlist:
        addr = td.xpath("./td[1]/text()")[0] + ":" + td.xpath("./td[2]/text()")[0]
        print("Testing", addr, end="")
        try:
            resp = requests.get(
                "https://www.baidu.com",
                proxies={
                    "http": "http://" + addr,
                    "https": "http://" + addr
                },
                timeout=5,
            )
            if resp.status_code == 200:
                print("...ok!")
                proxies.append(addr)
            else:
                print(f"...failed[{resp.status_code}]!")
        except Exception as e:
            print(f"...failed[{type ( e ).__name__}]!")


def getIP():
    global proxies
    proxies = []

    if os.path.exists("config\\proxies.txt"):
        print("加载代理IP中...")
        with open("config\\proxies.txt", "r") as file:
            for line in file:
                proxies.append(line.strip().split(' '))
        return

    print("获取代理IP中...")

    print("From zdaye.com")
    for page in range(1, 6):
        tr_list = etree.HTML(
            requests.get(
                f"https://www.zdaye.com/free/{page}/?ip=&adr=&checktime=&sleep=3&cunhuo=&dengji=&nadr=&https=&yys=&post=&px=3",
                headers=ua,
                verify=False).text).xpath("/html/body/div[3]/div/table/tbody")
        for tr in tr_list:
            addproxy(tr)

    print("From proxy.ip3366.net")
    for j in range(1, 6):
        print("  Page", str(j))
        url = f"https://proxy.ip3366.net/free/?action=china&page={j}"
        tr_list = etree.HTML(requests.get(
            url, headers=ua).text).xpath("/html/body/section/section/div[2]/table/tbody")
        for tr in tr_list:
            addproxy(tr)

    print("From www.ip3366.net")
    for i in [2, 1]:
        print("  Type", i)
        for j in range(1, 6):
            print("    Page", str(j))
            url = f"http://www.ip3366.net/free/?stype={i}&page={j}"
            addproxy(
                etree.HTML(requests.get(
                    url, headers=ua).text).xpath("/html/body/div[2]/div/div[2]/table/tbody/tr"))

    print("From www.kuaidaili.com")
    for x in ["inha", "intr"]:
        print("  " + x)
        for i in range(1, 6):
            print("    Page", str(i))
            url = "https://www.kuaidaili.com/free/" + x + "/" + str(i)
            tr_list = etree.HTML(requests.get(url, headers=ua).text).xpath(
                "/html/body/div/div[4]/div[2]/div[2]/div[2]/table/tbody")
            for tr in tr_list:
                addproxy(tr)

    with open("config\\proxies.txt", "w") as out:
        for x in proxies:
            out.write(x + "\n")


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.realpath(__file__)))
    getIP()
    # subprocess.Popen(f'bin\\aria2x.exe --conf-path=config\\aria2.conf')
    # c = Crawler()
    # if c.login():
    #     c.get_all()
