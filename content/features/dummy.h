
$cr c_dummy : c_enemy {
};

// Training dummies restore their health after all ordinary hit effects.
$c e_hit[1000](
    target: c_dummy,
    target: c_health& health
) {
    health.current = health.max;
};
