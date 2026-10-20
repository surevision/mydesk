extends Node3D

const CoinToss3DScript := preload("res://addons/dice_3d/coin_toss_3d.gd")
const RollerScript := preload("res://addons/dice_3d/dice_cinematic_roller_3d.gd")

@onready var _coin_toss: CoinToss3DScript = $CoinToss3D

var _next_value := 0


func _ready() -> void:
	_coin_toss.toss_finished.connect(_on_toss_finished)
	_coin_toss.toss(1)


func _unhandled_input(event: InputEvent) -> void:
	if not (event is InputEventKey) or not event.pressed or event.echo:
		return
	match event.keycode:
		KEY_SPACE:
			_coin_toss.toss(_next_value)
			_next_value = 1 - _next_value
		KEY_R:
			_coin_toss.toss(-1)
		KEY_UP:
			_set_gravity(RollerScript.GravityDirection.UP)
		KEY_DOWN:
			_set_gravity(RollerScript.GravityDirection.DOWN)
		KEY_LEFT:
			_set_gravity(RollerScript.GravityDirection.LEFT)
		KEY_RIGHT:
			_set_gravity(RollerScript.GravityDirection.RIGHT)


func _set_gravity(direction: int) -> void:
	_coin_toss.gravity_direction = direction
	print("[coin] gravity=%s" % ["Down", "Up", "Left", "Right"][direction])
	_coin_toss.toss(-1)


func _on_toss_finished(value: int) -> void:
	print("[coin] result=%d (%s)" % [value, "heads / H" if value == 1 else "tails / T"])
