/**
 * api.js
 * ---------------------------------------------------------------------------
 * 与 controller 的 Python HTTP 后端交互（config / ydk）。
 * 后端接口见 controller/server.py。
 */

/** 读取连接/行为配置 { center_ip, center_port, dice_coin_choose_player } */
export async function getConfig() {
  const res = await fetch("api/config", { cache: "no-store" });
  if (!res.ok) throw new Error("读取配置失败: " + res.status);
  return res.json();
}

/** 保存连接/行为配置，返回后端保存后的配置 */
export async function saveConfig(cfg) {
  const res = await fetch("api/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(cfg),
  });
  if (!res.ok) throw new Error("保存配置失败: " + res.status);
  return res.json();
}

/**
 * 上传 ydk 文件（multipart）。
 * @param {number} player 1 或 2
 * @param {File} file 浏览器 File 对象
 * @returns {Promise<{ok, player, ids, main, extra, side}>}
 */
export async function uploadYdk(player, file) {
  const fd = new FormData();
  fd.append("player", String(player));
  fd.append("file", file, file.name || "deck.ydk");
  const res = await fetch("api/ydk", { method: "POST", body: fd });
  if (!res.ok) throw new Error("ydk 上传失败: " + res.status);
  return res.json();
}

/** 以纯文本方式提交 ydk 内容（备用） */
export async function uploadYdkText(player, text) {
  const res = await fetch("api/ydk", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ player, content: text }),
  });
  if (!res.ok) throw new Error("ydk 解析失败: " + res.status);
  return res.json();
}
