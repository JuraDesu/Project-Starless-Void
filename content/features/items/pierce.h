
$cr c_item_pierce : c_item {
    int32 additional_hits = 2;

    r e_item_visual {
        ctx.name = "pierce";
        ctx.icon = item_icon<t_item_pierce>();
        ctx.valid = true;
    };
    r e_item_hover {
        if (ctx.stream)
            *ctx.stream << "pierces " << self.additional_hits
                        << " additional targets";
    };
    c e_item_inst_apply {
        ctx.additional_hits += self.additional_hits;
    };
};
