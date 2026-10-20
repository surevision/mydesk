class_name CoinToss3D
extends Node3D

## 基于 dice_3d 的硬币投掷节点。
##
## 内部使用 DiceCinematicRoller3D + 双面 COIN 骰子：硬币在屏幕空间内翻转、
## 弹跳，最终以指定的一面朝向结果方向（默认 -Z，即摄像机）。
##
## 用法：
##   $CoinToss3D.toss(1)   # 正面（H）
##   $CoinToss3D.toss(0)   # 反面（T）
##   $CoinToss3D.toss(-1)  # 随机
## 信号 toss_finished(value) 中 value 为 1（正面）/ 0（反面）。

signal toss_started()
signal toss_finished(value: int)

@export_category("Coin Toss")
## 未指定 coin_definition 时使用的硬币直径。
@export var coin_size: float = 2.6:
	set(value):
		coin_size = maxf(value, 0.1)
		if is_inside_tree() and coin_definition == null:
			_rebuild_coin()

## 自定义硬币定义；为空时自动创建默认金币。
@export var coin_definition: DiceDieDefinition3D:
	set(value):
		coin_definition = value
		if is_inside_tree():
			_rebuild_coin()

@export_group("Motion")
## 一次投掷的时长（秒）。
@export var toss_duration: float = 1.35
## 落地前的翻转圈数。
@export_range(0.0, 20.0, 0.01) var spin_turns: float = 6.0
## 翻腾过程中的弹跳高度。
@export var bounce_height: float = 1.1
## 弹跳次数。
@export var bounce_count: float = 2.0
## 弹跳的重力方向（从屏幕看）：Down / Up / Left / Right；弹跳弧线朝重力反方向。
@export_enum("Down", "Up", "Left", "Right") var gravity_direction: int = DiceCinematicRoller3D.GravityDirection.DOWN:
	set(value):
		gravity_direction = value
		if _roller != null:
			_roller.gravity_direction = value
## 结果面朝向：-Z 适合正对摄像机的平面投影。
@export_enum("+Y", "-Y", "+Z", "-Z", "+X", "-X") var result_side: int = DiceCinematicRoller3D.ResultSide.NEG_Z:
	set(value):
		result_side = value
		if _roller != null:
			_roller.result_side = value
## 显示舞台线框（调试用）。
@export var debug_visible: bool = false

@export_group("Visibility")
## 落地后保持显示的秒数；0 表示一直显示到下一次投掷。
@export var result_hold_seconds: float = 0.0

var _roller: DiceCinematicRoller3D
var _coin: DiceDie3D
var _tossing := false
var _hold_generation := 0
var _pending_toss: Variant = null


func _ready() -> void:
	_build()
	if _pending_toss != null:
		var pending: int = int(_pending_toss)
		_pending_toss = null
		toss(pending)


## 投掷硬币。value: 1=正面(H)，0=反面(T)，其它值=随机。
func toss(value: int = -1) -> void:
	if _coin == null:
		# 节点尚未 ready：记下请求，_ready 构建完成后自动执行。
		_pending_toss = value
		return
	_hold_generation += 1
	_tossing = true
	_coin.visible = true
	var requested: Variant = value if value == 0 or value == 1 else null
	_roller.roll(_coin, requested)
	toss_started.emit()


## 立即隐藏硬币。
func hide_coin() -> void:
	_hold_generation += 1
	_tossing = false
	if _coin != null:
		_coin.visible = false


func is_tossing() -> bool:
	return _tossing


func get_coin() -> DiceDie3D:
	return _coin


func _build() -> void:
	_ensure_roller()
	_apply_roller_settings()
	_rebuild_coin()


func _ensure_roller() -> void:
	if _roller != null and is_instance_valid(_roller):
		return
	_roller = get_node_or_null("Roller") as DiceCinematicRoller3D
	if _roller == null:
		_roller = DiceCinematicRoller3D.new()
		_roller.name = "Roller"
		add_child(_roller)
	if not _roller.roll_finished.is_connected(_on_roll_finished):
		_roller.roll_finished.connect(_on_roll_finished)


func _apply_roller_settings() -> void:
	_roller.debug_visible = debug_visible
	_roller.result_side = result_side
	# 硬币是薄片：不做“底面贴地”，让结果面直接朝向摄像机。
	_roller.align_flat_bottom_on_land = false
	_roller.spawn_dice_from_definitions_on_ready = false
	_roller.idle_spin_enabled = false
	_roller.idle_spin_after_result = false
	_roller.randomize_idle_start_side = false
	_roller.auto_layout_on_add_remove = false
	_roller.roll_duration = toss_duration
	_roller.spin_turns = spin_turns
	_roller.bounce_height = bounce_height
	_roller.bounce_count = bounce_count
	_roller.gravity_direction = gravity_direction


func _rebuild_coin() -> void:
	if _roller == null or not is_inside_tree():
		return

	if _coin != null and is_instance_valid(_coin):
		_roller.remove_die(_coin)
		_coin.queue_free()
		_coin = null

	var definition := coin_definition
	if definition == null:
		definition = DiceDieDefinition3D.coin(coin_size)

	_coin = _roller.create_die_from_definition(definition)
	_coin.visible = false
	_tossing = false


func _on_roll_finished(result: DiceRollResult) -> void:
	if result == null or result.die != _coin:
		return

	_tossing = false
	toss_finished.emit(result.value)

	if result_hold_seconds <= 0.0:
		return

	_hold_generation += 1
	var generation := _hold_generation
	get_tree().create_timer(result_hold_seconds).timeout.connect(
		func() -> void:
			if generation == _hold_generation and _coin != null:
				_coin.visible = false
	)
