extends SceneTree
var scene: Node = null
var frames := 0
func _initialize() -> void:
	print("DIAG start")
	create_timer(10.0).timeout.connect(func(): print("DIAG timeout"); quit(2))
	var packed: PackedScene = load("res://scenes/main.tscn")
	if packed == null:
		print("DIAG load failed"); quit(1); return
	scene = packed.instantiate()
	root.add_child(scene)
	var vp: Rect2 = root.get_visible_rect()
	print("DIAG viewport=", vp)
	print("DIAG window_size=", DisplayServer.window_get_size())
	print("DIAG content_scale=", root.content_scale_mode, " ", root.content_scale_factor)
	print("DIAG canvas_transform=", root.get_canvas_transform())
	for np in ["ui/player1/bling", "ui/player2/bling", "ui/player2/bling2"]:
		var ps: Node = scene.get_node_or_null(np)
		if ps == null:
			print("DIAG ", np, " MISSING"); continue
		var tp = ps.get("targetPath")
		var tgt: Control = ps.get_node_or_null(tp)
		if tgt == null:
			print("DIAG ", np, " target NOT FOUND ", tp); continue
		print("DIAG ", np, " tgt=", tp, " rect_at_ready=", tgt.get_global_rect())
	process_frame.connect(_on_frame)
	print("DIAG init done")
func _on_frame() -> void:
	frames += 1
	if frames == 5 or frames == 30:
		print("DIAG frame ", frames)
		for np in ["ui/player1/bling", "ui/player2/bling", "ui/player2/bling2"]:
			var ps: Node = scene.get_node_or_null(np)
			if ps == null:
				continue
			var tp = ps.get("targetPath")
			var tgt: Control = ps.get_node_or_null(tp)
			if tgt == null:
				continue
			print("DIAG ", np, " rect=", tgt.get_global_rect(), " pos=", ps.global_position)
			print("DIAG ", np, " canvas_xf=", root.get_canvas_transform())
	if frames >= 31:
		quit(0)
