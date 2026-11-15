"""Measure WCAG contrast for the interface's actual primary foreground/background pairs."""
import json

from scripts.common import ROOT,json_write


def luminance(hex_color):
    channels=[int(hex_color[i:i+2],16)/255 for i in (1,3,5)]
    linear=[c/12.92 if c <= .04045 else ((c+.055)/1.055)**2.4 for c in channels]
    return sum(c*w for c,w in zip(linear,(.2126,.7152,.0722)))


def main():
    pairs={"body":("#E8F0FA","#0A0F1B"),"surface text":("#E8F0FA","#121D2E"),"muted":("#A5B4C8","#121D2E"),
           "secondary":("#8B9DB4","#121D2E"),"cyan link":("#65D8E7","#121D2E"),"amber limitation":("#FFB963","#281F19"),
           "button":("#0A1822","#65D8E7"),"coverage count":("#65D8E7","#173D4A")}
    report=[]
    for name,(foreground,background) in pairs.items():
        hi,lo=sorted((luminance(foreground),luminance(background)),reverse=True)
        ratio=(hi+.05)/(lo+.05)
        report.append({"pair":name,"foreground":foreground,"background":background,"ratio":round(ratio,2),"aa_normal_text":ratio >=4.5})
    json_write(ROOT/"artifacts/contrast.json",report)
    print(json.dumps(report,indent=2))
    if not all(r["aa_normal_text"] for r in report):raise SystemExit(1)


if __name__ == "__main__":main()
