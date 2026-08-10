
$cr c_item_damage : c_item {
    int32 amount = 4;

    r e_item_visual {
        ctx.name = "damage";
        ctx.icon = item_icon<t_invalid>();
        ctx.valid = true;
    };

    r e_item_hover {
        if (ctx.stream)
            *ctx.stream << "adds " << damage(self.amount)
                        << " projectile damage";
    };

    c e_item_inst_apply {
        ctx.damage_bonus += self.amount;
    };
};
