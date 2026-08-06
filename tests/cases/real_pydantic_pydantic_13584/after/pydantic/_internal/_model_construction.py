                    from annotationlib import Format, call_annotate_function, get_annotate_from_class_namespace

                    if annotate := get_annotate_from_class_namespace(namespace):
                        try:
                            # Try the VALUE format first, as it is way more expensive to use the FORWARDREF format:
                            raw_annotations = call_annotate_function(annotate, format=Format.VALUE)
                        except Exception:
                            raw_annotations = call_annotate_function(annotate, format=Format.FORWARDREF)
                    else:
                        raw_annotations = {}
            else:
