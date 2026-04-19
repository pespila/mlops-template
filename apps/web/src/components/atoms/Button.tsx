import { forwardRef, type ButtonHTMLAttributes, type ReactElement, type ReactNode } from "react";
import { Link, type LinkProps } from "react-router-dom";

import { cn } from "@/lib/cn";

export type ButtonVariant = "primary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md";

interface CommonProps {
  variant?: ButtonVariant;
  size?: ButtonSize;
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
  className?: string;
  children?: ReactNode;
}

type ButtonAsButton = CommonProps &
  Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> & {
    asChild?: false;
    as?: "button";
  };

interface ButtonAsAnchor extends CommonProps {
  asChild: true;
  as: "a";
  href: string;
  target?: string;
  rel?: string;
  onClick?: (ev: React.MouseEvent<HTMLAnchorElement>) => void;
}

interface ButtonAsLink extends CommonProps {
  asChild: true;
  as: "link";
  to: LinkProps["to"];
  onClick?: (ev: React.MouseEvent<HTMLAnchorElement>) => void;
}

export type ButtonProps = ButtonAsButton | ButtonAsAnchor | ButtonAsLink;

const sizeClasses: Record<ButtonSize, string> = {
  sm: "text-[13px] px-3.5 py-1.5 gap-1.5",
  md: "text-sm px-5 py-2.5 gap-2",
};

const variantClasses: Record<ButtonVariant, string> = {
  primary: "btn-primary",
  ghost: "btn-ghost",
  danger:
    "inline-flex items-center justify-center rounded bg-danger text-white font-semibold " +
    "transition-[filter,transform] duration-150 ease-[var(--ease-out)] hover:brightness-105 " +
    "hover:-translate-y-[2px] active:translate-y-0 disabled:opacity-50 disabled:hover:translate-y-0",
};

function composeClasses(
  variant: ButtonVariant,
  size: ButtonSize,
  className: string | undefined,
): string {
  const base =
    "inline-flex items-center justify-center whitespace-nowrap font-sans font-semibold " +
    "select-none disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-none";
  return cn(base, variantClasses[variant], sizeClasses[size], className);
}

function Content({
  leftIcon,
  rightIcon,
  children,
}: {
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
  children: ReactNode;
}) {
  return (
    <>
      {leftIcon ? <span aria-hidden="true">{leftIcon}</span> : null}
      {children}
      {rightIcon ? <span aria-hidden="true">{rightIcon}</span> : null}
    </>
  );
}

export const Button = forwardRef<HTMLButtonElement | HTMLAnchorElement, ButtonProps>(
  function Button(props, ref): ReactElement {
    const variant = props.variant ?? "primary";
    const size = props.size ?? "md";
    const classes = composeClasses(variant, size, props.className);
    const content = (
      <Content leftIcon={props.leftIcon} rightIcon={props.rightIcon}>
        {props.children}
      </Content>
    );

    if ("asChild" in props && props.asChild && props.as === "a") {
      return (
        <a
          ref={ref as React.Ref<HTMLAnchorElement>}
          href={props.href}
          target={props.target}
          rel={props.rel}
          className={classes}
          onClick={props.onClick}
        >
          {content}
        </a>
      );
    }

    if ("asChild" in props && props.asChild && props.as === "link") {
      return (
        <Link
          ref={ref as React.Ref<HTMLAnchorElement>}
          to={props.to}
          className={classes}
          onClick={props.onClick}
        >
          {content}
        </Link>
      );
    }

    const buttonProps = props as ButtonAsButton;
    const {
      asChild: _asChild,
      as: _as,
      variant: _v,
      size: _s,
      leftIcon: _li,
      rightIcon: _ri,
      className: _cn,
      children: _c,
      ...domProps
    } = buttonProps;
    // Intentionally discarding component-only props.
    void _asChild;
    void _as;
    void _v;
    void _s;
    void _li;
    void _ri;
    void _cn;
    void _c;
    return (
      <button
        ref={ref as React.Ref<HTMLButtonElement>}
        type={domProps.type ?? "button"}
        className={classes}
        {...domProps}
      >
        {content}
      </button>
    );
  },
);
