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
from concurrent.futures import ThreadPoolExecutor

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


class Exporter:

    def __init__(self):
        self.session = requests.sessions.Session()
        self.session.headers.update({
            "user-agent":
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Safari/537.36 Edg/106.0.1370.37"
        })
        self.conf = configparser.ConfigParser()
        self.account: str = None
        self.password: str = None

    def readConfig(self) -> bool:
        try:
            self.conf.read('config\\main.ini')
            self.account = self.conf.get("user", "account")
            self.password = self.conf.get("user", "password")
            if self.conf.has_option("download", "dir"):
                self.downdir = self.conf.get("download", "dir")
            else:
                self.downdir = 'D:\DaPengExport'
            if not os.path.exists(self.downdir):
                os.makedirs(self.downdir)
        except FileNotFoundError:
            print("读取配置失败: 未找到配置文件. 自动生成空白文件, 请填写后重试.")
            with open('config\\main.ini') as main_ini:
                main_ini.write(main_ini_default)
            return None
        except (configparser.NoSectionError, configparser.NoOptionError):
            print("读取配置失败: 配置错误")
            return None

    def getCookie(self) -> None:
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

    def login(self) -> bool:
        if not self.account or not self.password:
            print("登陆失败: 请先读取用户名密码")
            return False
        try:
            if not self.conf.has_option("user", "cookie") or self.conf.get("user", "cookie") == "":
                self.getCookie()
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
            self.conf.set("user", "cookie", json.dumps(json.dumps(self.session.cookies.get_dict())))
        except requests.exceptions.RequestException:
            print("登陆失败: 网络错误")
            return False
        except Exception as e:
            print("登陆失败:", __name__ ( e ))
        else:
            print ( "登陆成功!" )
            with open ( 'config\\main.ini', 'w' ) as fp:
                self.conf.write ( fp )
            return True

    def job(self, m3u8_url: str, key_url: str, vtitle: str, download_dir: str) -> None:
        print("开始下载", m3u8_url)
        print(m3u8_url, "->", download_dir)
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
            proxy = proxies[randint(0, len(proxies) - 1)]
            jobs.append((
                client.addUri([ts], {
                    "dir": download_dir + "ts/",
                    "out": str(index) + ".ts"
                }),
                index,
                ts,
            ))
        for x, index, ts in jobs:
            while True:
                y = client.tellStatus(x)["status"]
                if y == "complete":
                    break
                elif y == "error":
                    proxy = proxies[randint(0, len(proxies) - 1)]
                    print(f"下载 {index}.ts 时出现错误, 使用代理 {proxy[0]} 重试.")
                    xx = client.addUri(
                        [ts],
                        {
                            "dir": download_dir + "ts/",
                            "out": str(index) + ".ts",
                            "all-proxy": 'http://' + proxy[0],
                            "all-proxy-user": proxy[1],
                            "all-proxy-passwd": proxy[2]
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
        print("合并中...")
        subprocess.run(
            f'bin\\ffmpeg.exe -allowed_extensions ALL -i "{download_dir}ts/index.m3u8" -c copy -vtag hvc1 "{download_dir+vtitle}.mp4" -v fatal -y',
            shell=True,
        )
        print("删除临时文件...")
        subprocess.run(
            f'rd /s /q {download_dir}ts/',
            shell=True,
        )

    def get_all(self) -> None:
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


class AgentIPCrawler:

    def __init__(self):
        self.tpool = ThreadPoolExecutor(max_workers=32)
        self.proxies: list[list[str, str, str]] = []
        self.raw_proxies: list[list[str, str, str]] = []

    def testproxy(self, addr: str) -> list:
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
                return [addr, "", ""]
            else:
                return []
        except Exception as e:
            return []

    def parseFromTDList(self, tdlist):
        for td in tdlist:
            self.raw_proxies.append(
                td.xpath("./td[1]/text()")[0].strip() + ":" + td.xpath("./td[2]/text()")[0].strip())

    def getIP(self) -> None:

        global proxies

        print("获取代理IP中...")

        print("来自 zdaye.com")
        for page in range(1, 5):
            tr_list = etree.HTML(
                requests.get(
                    f"https://www.zdaye.com/free/{page}/?ip=&adr=&checktime=&sleep=2&cunhuo=&dengji=&nadr=&https=&yys=&post=&px=3",
                    headers=ua,
                    verify=False).text).xpath("/html/body/div[3]/div/table/tbody")
            for tr in tr_list:
                self.parseFromTDList(tr)

        print("来自 proxy.ip3366.net")
        for page in range(1, 7):
            print("   第", str(page), "页")
            url = f"https://proxy.ip3366.net/free/?action=china&page={page}"
            tr_list = etree.HTML(requests.get(
                url, headers=ua).text).xpath("/html/body/section/section/div[2]/table/tbody")
            for tr in tr_list:
                self.parseFromTDList(tr)

        print("来自 www.ip3366.net")
        for type in [1, 2]:
            print("  类型", type)
            for page in range(1, 6):
                print("    第", str(page), "页")
                url = f"http://www.ip3366.net/free/?stype={type}&page={page}"
                self.parseFromTDList(
                    etree.HTML(requests.get(
                        url, headers=ua).text).xpath("/html/body/div[2]/div/div[2]/table/tbody/tr"))

        print("来自 www.kuaidaili.com")
        for type in ["inha", "intr"]:
            print("  类型", type)
            for page in range(1, 10):
                print("    第", str(page), "页")
                url = "https://www.kuaidaili.com/free/" + type + "/" + str(page)
                tr_list = etree.HTML(requests.get(url, headers=ua).text).xpath(
                    "/html/body/div/div[4]/div[2]/div[2]/div[2]/table/tbody")
                for tr in tr_list:
                    self.parseFromTDList(tr)

        print("来自 www.89ip.cn")
        for page in range(1, 7):
            print("  第", str(page), "页")
            url = f"https://www.89ip.cn/index_{page}.html"
            html = requests.get(url, headers=ua).text
            tr_list = etree.HTML(html).xpath("/html/body/div[4]/div[1]/div/div[1]/table/tbody")
            for tr in tr_list:
                self.parseFromTDList(tr)

        print("测速中...")
        self.proxies = self.tpool.map(self.testproxy, self.raw_proxies).remove([])

        proxies = self.proxies

    def loadFile(self) -> bool:
        try:
            with open("config\\proxies.txt", "r") as file:
                for line in file:
                    proxy = line.strip().split(' ')
                    if len(proxy) == 1:
                        proxy.append("")
                        proxy.append("")
                    self.proxies.append(proxy)
        except Exception as e:
            return False
        else:
            return True

    def saveFile(self) -> None:
        with open("config\\proxies.txt", "w") as out:
            for x in self.proxies:
                out.write(x + "\n")


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.realpath(__file__)))
    c = AgentIPCrawler()
    if not c.loadFile():
        c.getIP()
        c.saveFile()
    c = Exporter()
    c.readConfig()
    if c.login():
        subprocess.Popen(f'bin\\aria2x.exe --conf-path=config\\aria2.conf')
        c.get_all()
