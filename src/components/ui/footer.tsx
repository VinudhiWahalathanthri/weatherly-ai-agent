import React from "react";

import { motion, useMotionValue, useTransform } from "framer-motion";
import { Facebook, Instagram, Twitter, Linkedin } from "lucide-react";
const Footer: React.FC = () => (
  <footer className="bg-black text-gray-300 ">
    <div className="max-w-7xl mx-auto py-12 px-6 grid grid-cols-1 md:grid-cols-4 gap-10">
      <div>
        <motion.img
          src="src/assets/Weatherly.svg"
          alt="Logo"
          className="h-14 mb-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
        />
        <motion.h3
          className="font-semibold text-white mb-2"
          initial={{ y: 6, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
        >
          Weatherly
        </motion.h3>
        <motion.p
          className="text-sm leading-relaxed"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1, transition: { delay: 0.08 } }}
        >
          Weatherly is a modern, intuitive web application that delivers precise
          and up-to-date weather information directly from{" "}
          <span style={{ fontWeight: "bold", color: "#FFC107" }}>NASA’s</span>
          {"\n"}
          datasets.
        </motion.p>
        <div className="mt-3 space-x-2 text-sm">
          <a href="#mission" className="text-blue-400 hover:underline">
            About Our Mission
          </a>{" "}
          •{" "}
          <a href="#join" className="text-blue-400 hover:underline">
            Join Us →
          </a>
        </div>
      </div>

      <div>
        <h4 className="font-semibold text-white mb-3">Explore</h4>
        <ul className="space-y-2 text-sm">
          <li>
            <a href="#home" className="hover:underline">
              Home
            </a>
          </li>
          <li>
            <a href="#news" className="hover:underline">
              News & Events
            </a>
          </li>
          <li>
            <a href="#multimedia" className="hover:underline">
              Multimedia
            </a>
          </li>
          <li>
            <a href="#missions" className="hover:underline">
              Missions
            </a>
          </li>
        </ul>
      </div>

      <div>
        <h4 className="font-semibold text-white mb-3">Discover</h4>
        <ul className="space-y-2 text-sm">
          <li>
            <a href="#space" className="hover:underline">
              Humans in Space
            </a>
          </li>
          <li>
            <a href="#earth" className="hover:underline">
              Earth
            </a>
          </li>
          <li>
            <a href="#solar" className="hover:underline">
              The Solar System
            </a>
          </li>
          <li>
            <a href="#universe" className="hover:underline">
              The Universe
            </a>
          </li>
          <li>
            <a href="#science" className="hover:underline">
              Science
            </a>
          </li>
        </ul>
      </div>

      <div>
        <h4 className="font-semibold text-white mb-3">Connect</h4>
        <ul className="space-y-2 text-sm">
          <li>
            <a href="#aeronautics" className="hover:underline">
              Aeronautics
            </a>
          </li>
          <li>
            <a href="#technology" className="hover:underline">
              Technology
            </a>
          </li>
          <li>
            <a href="#resources" className="hover:underline">
              Learning Resources
            </a>
          </li>
          <li>
            <a href="#about" className="hover:underline">
              About Us
            </a>
          </li>
          <li>
            <a href="#spanish" className="hover:underline">
              En Español
            </a>
          </li>
        </ul>

        <div className="flex gap-4 mt-4 text-gray-400">
          <motion.div whileHover={{ y: -4 }}>
            <Facebook className="w-5 h-5 hover:text-white cursor-pointer" />
          </motion.div>
          <motion.div whileHover={{ y: -4 }}>
            <Instagram className="w-5 h-5 hover:text-white cursor-pointer" />
          </motion.div>
          <motion.div whileHover={{ y: -4 }}>
            <Twitter className="w-5 h-5 hover:text-white cursor-pointer" />
          </motion.div>
          <motion.div whileHover={{ y: -4 }}>
            <Linkedin className="w-5 h-5 hover:text-white cursor-pointer" />
          </motion.div>
        </div>
      </div>
    </div>

    <div className="border-t border-gray-700 py-4 text-xs text-center text-gray-400">
      Page Last Updated: <span className="font-semibold">Oct 10, 2025</span> •
      Page Editor: <span className="font-semibold">Ceylon XZORA</span> •
      Responsible Official:{" "}
      <span className="font-semibold">Ceylon XZORA</span>
    </div>
  </footer>
);

export default Footer;
